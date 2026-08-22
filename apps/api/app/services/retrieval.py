"""Workspace-scoped dense retrieval orchestration."""

from dataclasses import dataclass

from app.core.caller import CallerContext
from app.repositories.documents import DocumentNotFoundError, DocumentRepository
from app.repositories.retrieval import DenseRetrievalRepository, RetrievedChunkRow
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderUnavailableError,
)


class RetrievalInvalidQueryError(Exception):
    pass


class RetrievalDocumentNotReadyError(Exception):
    pass


class RetrievalEmbeddingUnavailableError(Exception):
    pass


class RetrievalError(Exception):
    pass


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    distance: float
    similarity: float
    page_start: int | None
    page_end: int | None
    section: str | None
    heading: str | None
    source_block_start: int
    source_block_end: int


class DenseRetrievalService:
    def __init__(
        self,
        *,
        caller: CallerContext,
        document_repository: DocumentRepository,
        retrieval_repository: DenseRetrievalRepository,
        embedding_provider: EmbeddingProvider,
        default_limit: int,
        max_limit: int,
        expected_dimension: int,
        hnsw_ef_search: int,
    ) -> None:
        self._caller = caller
        self._document_repository = document_repository
        self._retrieval_repository = retrieval_repository
        self._embedding_provider = embedding_provider
        self._default_limit = default_limit
        self._max_limit = max_limit
        self._expected_dimension = expected_dimension
        self._hnsw_ef_search = hnsw_ef_search

    def search(
        self, *, query: str, limit: int | None = None, document_ids: tuple[str, ...] = ()
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise RetrievalInvalidQueryError("Query must not be blank.")
        resolved_limit = self._default_limit if limit is None else limit
        if resolved_limit < 1 or resolved_limit > self._max_limit:
            raise RetrievalInvalidQueryError("Retrieval limit is invalid.")
        for document_id in document_ids:
            try:
                document = self._document_repository.get(
                    workspace_id=self._caller.id, document_id=document_id
                )
            except DocumentNotFoundError:
                raise
            if document.ingestion_status != "embedded":
                raise RetrievalDocumentNotReadyError("Document is not embedded.")
        try:
            vector = self._embedding_provider.embed_query(query.strip())
            dimension = self._embedding_provider.dimension
        except EmbeddingProviderUnavailableError as error:
            raise RetrievalEmbeddingUnavailableError("Embedding model is unavailable.") from error
        except EmbeddingProviderError as error:
            raise RetrievalError("Query embedding failed.") from error
        except Exception as error:
            raise RetrievalError("Query embedding failed.") from error
        if dimension != self._expected_dimension or len(vector) != self._expected_dimension:
            raise RetrievalError("Query embedding has an invalid dimension.")
        try:
            rows = self._retrieval_repository.search(
                workspace_id=self._caller.id,
                query_vector=vector,
                model_id=self._embedding_provider.model_id,
                dimension=dimension,
                limit=resolved_limit,
                document_ids=tuple(dict.fromkeys(document_ids)),
                hnsw_ef_search=self._hnsw_ef_search,
            )
        except Exception as error:
            raise RetrievalError("Dense retrieval failed.") from error
        return [_to_result(row) for row in rows]


def _to_result(row: RetrievedChunkRow) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        filename=row.filename,
        chunk_index=row.chunk_index,
        text=row.text,
        distance=row.distance,
        similarity=1.0 - row.distance,
        page_start=row.page_start,
        page_end=row.page_end,
        section=row.section,
        heading=row.heading,
        source_block_start=row.source_block_start,
        source_block_end=row.source_block_end,
    )
