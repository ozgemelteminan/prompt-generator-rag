"""Database persistence for workspace-scoped document metadata."""

from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DocumentBlockRecord, DocumentChunkRecord, DocumentRecord
from app.document_processing.models import DocumentChunk, NormalizedDocument, TextBlock


class DocumentNotFoundError(Exception):
    """Raised when a document is absent from the current workspace."""


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_duplicate(self, *, workspace_id: str, checksum: str) -> DocumentRecord | None:
        return self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.workspace_id == workspace_id,
                DocumentRecord.checksum == checksum,
            )
        )

    def create(self, record: DocumentRecord) -> DocumentRecord:
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return record

    def list(self, *, workspace_id: str) -> list[DocumentRecord]:
        return list(
            self._session.scalars(
                select(DocumentRecord)
                .where(DocumentRecord.workspace_id == workspace_id)
                .order_by(DocumentRecord.created_at.desc())
            )
        )

    def get(self, *, workspace_id: str, document_id: str) -> DocumentRecord:
        record = self._session.scalar(
            select(DocumentRecord).where(
                DocumentRecord.workspace_id == workspace_id,
                DocumentRecord.id == document_id,
            )
        )
        if record is None:
            raise DocumentNotFoundError("Document was not found in this workspace.")
        return record

    def delete(self, record: DocumentRecord) -> None:
        self._session.delete(record)
        self._session.commit()

    def mark_processing(self, record: DocumentRecord) -> None:
        record.ingestion_status = "processing"
        self._session.commit()
        self._session.refresh(record)

    def replace_normalized_content(
        self, record: DocumentRecord, document: NormalizedDocument
    ) -> DocumentRecord:
        try:
            self._session.execute(
                delete(DocumentBlockRecord).where(DocumentBlockRecord.document_id == record.id)
            )
            self._session.add_all(
                [
                    DocumentBlockRecord(
                        id=str(uuid4()),
                        document_id=record.id,
                        order_index=block.order_index,
                        block_type=block.block_type,
                        text=block.text,
                        page_number=block.page_number,
                        heading_level=block.heading_level,
                        section=block.section,
                    )
                    for block in document.blocks
                ]
            )
            record.language = document.language
            record.ingestion_status = "parsed"
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._session.refresh(record)
        return record

    def mark_failed(self, record: DocumentRecord) -> None:
        self._session.rollback()
        record = self._session.merge(record)
        record.ingestion_status = "failed"
        self._session.commit()

    def get_blocks(self, record: DocumentRecord) -> tuple[TextBlock, ...]:
        rows = self._session.scalars(
            select(DocumentBlockRecord)
            .where(DocumentBlockRecord.document_id == record.id)
            .order_by(DocumentBlockRecord.order_index)
        )
        return tuple(
            TextBlock(
                block_type=row.block_type,  # type: ignore[arg-type]
                text=row.text,
                order_index=row.order_index,
                page_number=row.page_number,
                heading_level=row.heading_level,
                section=row.section,
            )
            for row in rows
        )

    def mark_chunking(self, record: DocumentRecord) -> None:
        record.ingestion_status = "chunking"
        self._session.commit()
        self._session.refresh(record)

    def replace_chunks(self, record: DocumentRecord, chunks: tuple[DocumentChunk, ...]) -> None:
        try:
            self._session.execute(
                delete(DocumentChunkRecord).where(DocumentChunkRecord.document_id == record.id)
            )
            self._session.add_all(
                [
                    DocumentChunkRecord(
                        id=chunk.id,
                        workspace_id=chunk.workspace_id,
                        document_id=chunk.document_id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        token_count=chunk.token_count,
                        language=chunk.language,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        section=chunk.section,
                        heading=chunk.heading,
                        source_block_start=chunk.source_block_start,
                        source_block_end=chunk.source_block_end,
                    )
                    for chunk in chunks
                ]
            )
            record.ingestion_status = "chunked"
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._session.refresh(record)
