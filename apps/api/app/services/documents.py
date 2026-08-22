"""Document upload use case: validate, deduplicate, store, and persist metadata."""

import hashlib
import zipfile
from collections.abc import Awaitable
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Protocol
from uuid import uuid4

from app.core.caller import CallerContext
from app.db.models import DocumentRecord
from app.document_processing.chunking import StructureAwareChunker
from app.document_processing.models import ChunkingConfig, ChunkStatistics, DocumentMetadata
from app.document_processing.normalization import normalize_document
from app.document_processing.parsing import DocumentParserError
from app.infrastructure.document_parsers import DocumentParserRegistry
from app.infrastructure.local_document_storage import DocumentStorageError
from app.repositories.documents import DocumentRepository
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
)


class UploadSource(Protocol):
    filename: str | None

    def read(self, size: int = -1) -> Awaitable[bytes]: ...


class DocumentStorage(Protocol):
    def save(self, *, workspace_id: str, document_id: str, content: bytes) -> str: ...

    def delete(self, storage_key: str) -> None: ...

    def read(self, storage_key: str) -> bytes: ...


class DocumentUploadError(Exception):
    """Base error for safe document upload failures."""


class DocumentEmptyError(DocumentUploadError):
    pass


class DocumentTooLargeError(DocumentUploadError):
    pass


class DocumentUnsupportedTypeError(DocumentUploadError):
    pass


class DocumentInvalidFilenameError(DocumentUploadError):
    pass


class DocumentProcessingError(Exception):
    """Base error for safe document processing failures."""


class DocumentNoExtractableTextError(DocumentProcessingError):
    pass


class DocumentParseError(DocumentProcessingError):
    pass


class DocumentNotParsedError(DocumentProcessingError):
    pass


class DocumentChunkingError(DocumentProcessingError):
    pass


class DocumentNotChunkedError(DocumentProcessingError):
    pass


class DocumentEmbeddingModelUnavailableError(DocumentProcessingError):
    pass


class DocumentEmbeddingError(DocumentProcessingError):
    pass


class DocumentEmbeddingDimensionMismatchError(DocumentProcessingError):
    pass


class DocumentVectorPersistenceError(DocumentProcessingError):
    pass


@dataclass(frozen=True)
class DocumentUploadResult:
    record: DocumentRecord
    deduplicated: bool


@dataclass(frozen=True)
class DocumentChunkingResult:
    record: DocumentRecord
    statistics: ChunkStatistics


@dataclass(frozen=True)
class DocumentEmbeddingResult:
    record: DocumentRecord
    chunk_count: int
    embedded_chunk_count: int
    embedding_model: str


class DocumentService:
    """Keep upload I/O, metadata persistence, and local storage outside routes."""

    def __init__(
        self,
        *,
        caller: CallerContext,
        repository: DocumentRepository,
        storage: DocumentStorage,
        max_upload_bytes: int,
        parser_registry: DocumentParserRegistry | None = None,
        chunker: StructureAwareChunker | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_batch_size: int = 32,
        embedding_dimension: int | None = None,
    ) -> None:
        self._caller = caller
        self._repository = repository
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes
        self._parser_registry = parser_registry or DocumentParserRegistry()
        self._chunker = chunker or StructureAwareChunker(ChunkingConfig())
        self._embedding_provider = embedding_provider
        self._embedding_batch_size = embedding_batch_size
        self._embedding_dimension = embedding_dimension

    async def upload(self, source: UploadSource) -> DocumentUploadResult:
        filename = _safe_filename(source.filename)
        content = await source.read(self._max_upload_bytes + 1)
        if not content:
            raise DocumentEmptyError("Document file is empty.")
        if len(content) > self._max_upload_bytes:
            raise DocumentTooLargeError("Document file exceeds the upload limit.")
        media_type = detect_media_type(content, filename)
        checksum = hashlib.sha256(content).hexdigest()
        existing = self._repository.find_duplicate(workspace_id=self._caller.id, checksum=checksum)
        if existing is not None:
            return DocumentUploadResult(record=existing, deduplicated=True)

        document_id = str(uuid4())
        storage_key = self._storage.save(
            workspace_id=self._caller.id,
            document_id=document_id,
            content=content,
        )
        record = DocumentRecord(
            id=document_id,
            workspace_id=self._caller.id,
            original_filename=filename,
            media_type=media_type,
            file_size=len(content),
            checksum=checksum,
            ingestion_status="uploaded",
            storage_key=storage_key,
        )
        try:
            return DocumentUploadResult(record=self._repository.create(record), deduplicated=False)
        except Exception:
            try:
                self._storage.delete(storage_key)
            except DocumentStorageError:
                pass
            raise

    def list(self) -> list[DocumentRecord]:
        return self._repository.list(workspace_id=self._caller.id)

    def get(self, document_id: str) -> DocumentRecord:
        return self._repository.get(workspace_id=self._caller.id, document_id=document_id)

    def delete(self, document_id: str) -> None:
        record = self.get(document_id)
        self._storage.delete(record.storage_key)
        self._repository.delete(record)

    def process(self, document_id: str) -> DocumentRecord:
        record = self.get(document_id)
        self._repository.mark_processing(record)
        try:
            content = self._storage.read(record.storage_key)
            parser = self._parser_registry.for_media_type(record.media_type)
            parsed = parser.parse(
                content,
                DocumentMetadata(document_id=record.id, media_type=record.media_type),
            )
            normalized = normalize_document(parsed)
            if not normalized.blocks:
                raise DocumentNoExtractableTextError("No extractable text was found.")
            return self._repository.replace_normalized_content(record, normalized)
        except DocumentNoExtractableTextError:
            self._repository.mark_failed(record)
            raise
        except DocumentParserError as error:
            self._repository.mark_failed(record)
            raise DocumentParseError("Document parsing failed.") from error
        except DocumentStorageError:
            self._repository.mark_failed(record)
            raise

    def chunk(self, document_id: str) -> DocumentChunkingResult:
        record = self.get(document_id)
        if record.ingestion_status not in {"parsed", "chunked"}:
            raise DocumentNotParsedError("Document must be parsed before chunking.")
        self._repository.mark_chunking(record)
        try:
            blocks = self._repository.get_blocks(record)
            if not blocks:
                raise DocumentNotParsedError("Document has no parsed blocks.")
            chunks = self._chunker.chunk(
                document_id=record.id,
                workspace_id=self._caller.id,
                language=record.language,
                blocks=blocks,
            )
            if not chunks:
                raise DocumentChunkingError("Document produced no chunks.")
            self._repository.replace_chunks(record, chunks)
            return DocumentChunkingResult(
                record=record, statistics=self._chunker.statistics(chunks)
            )
        except (DocumentNotParsedError, DocumentChunkingError):
            self._repository.mark_failed(record)
            raise
        except Exception as error:
            self._repository.mark_failed(record)
            raise DocumentChunkingError("Document chunking failed.") from error

    def embed(self, document_id: str) -> DocumentEmbeddingResult:
        record = self.get(document_id)
        if record.ingestion_status not in {"chunked", "embedded"}:
            raise DocumentNotChunkedError("Document must be chunked before embedding.")
        if self._embedding_provider is None:
            raise DocumentEmbeddingModelUnavailableError("Embedding model is not configured.")

        chunks = self._repository.get_chunks(record)
        if not chunks:
            raise DocumentNotChunkedError("Document has no chunks to embed.")
        self._repository.mark_embedding(record)
        try:
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), self._embedding_batch_size):
                batch = chunks[start : start + self._embedding_batch_size]
                vectors.extend(
                    self._embedding_provider.embed_passages([chunk.text for chunk in batch])
                )
            dimension = self._embedding_provider.dimension
        except EmbeddingProviderUnavailableError as error:
            self._repository.mark_failed(record)
            raise DocumentEmbeddingModelUnavailableError(
                "Embedding model is unavailable."
            ) from error
        except EmbeddingProviderError as error:
            self._repository.mark_failed(record)
            raise DocumentEmbeddingError("Document embedding failed.") from error
        except Exception as error:
            self._repository.mark_failed(record)
            raise DocumentEmbeddingError("Document embedding failed.") from error

        expected_dimension = self._embedding_dimension or dimension
        if (
            len(vectors) != len(chunks)
            or dimension != expected_dimension
            or any(len(vector) != expected_dimension for vector in vectors)
        ):
            self._repository.mark_failed(record)
            raise DocumentEmbeddingDimensionMismatchError("Embedding dimension is invalid.")
        try:
            persisted = self._repository.replace_embeddings(
                record,
                embeddings=list(zip(chunks, vectors, strict=True)),
                model_id=self._embedding_provider.model_id,
                dimension=dimension,
            )
        except Exception as error:
            self._repository.mark_failed(record)
            raise DocumentVectorPersistenceError("Vectors could not be persisted.") from error
        return DocumentEmbeddingResult(
            record=persisted,
            chunk_count=len(chunks),
            embedded_chunk_count=len(vectors),
            embedding_model=self._embedding_provider.model_id,
        )


def _safe_filename(filename: str | None) -> str:
    if not filename:
        raise DocumentInvalidFilenameError("Document filename is required.")
    safe_name = PurePath(filename.replace("\\", "/")).name
    if safe_name in {"", ".", ".."} or len(safe_name) > 255:
        raise DocumentInvalidFilenameError("Document filename is invalid.")
    return safe_name


def detect_media_type(content: bytes, filename: str) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if _is_docx(content):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if _is_safe_utf8_text(content) and filename.lower().endswith(".md"):
        return "text/markdown"
    if _is_safe_utf8_text(content) and filename.lower().endswith(".txt"):
        return "text/plain"
    raise DocumentUnsupportedTypeError("Document type is not supported.")


def _is_docx(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _is_safe_utf8_text(content: bytes) -> bool:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return "\x00" not in text
