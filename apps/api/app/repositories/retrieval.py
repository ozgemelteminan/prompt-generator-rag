"""Database-scoped dense retrieval over persisted pgvector embeddings."""

from dataclasses import dataclass
from math import sqrt

from sqlalchemy import Float, select, text
from sqlalchemy.orm import Session

from app.db.models import DocumentChunkRecord, DocumentEmbeddingRecord, DocumentRecord


@dataclass(frozen=True)
class RetrievedChunkRow:
    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    distance: float
    page_start: int | None
    page_end: int | None
    section: str | None
    heading: str | None
    source_block_start: int
    source_block_end: int


class DenseRetrievalRepository:
    """Keep workspace/model filters inside the vector query itself."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self,
        *,
        workspace_id: str,
        query_vector: list[float],
        model_id: str,
        dimension: int,
        limit: int,
        document_ids: tuple[str, ...] = (),
        hnsw_ef_search: int = 100,
    ) -> list[RetrievedChunkRow]:
        filters = [
            DocumentEmbeddingRecord.workspace_id == workspace_id,
            DocumentEmbeddingRecord.embedding_model_id == model_id,
            DocumentEmbeddingRecord.embedding_dimension == dimension,
        ]
        if document_ids:
            filters.append(DocumentEmbeddingRecord.document_id.in_(document_ids))
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            return self._search_postgres(
                filters=filters,
                query_vector=query_vector,
                limit=limit,
                hnsw_ef_search=hnsw_ef_search,
            )
        return self._search_sqlite(filters=filters, query_vector=query_vector, limit=limit)

    def _search_postgres(
        self,
        *,
        filters: list[object],
        query_vector: list[float],
        limit: int,
        hnsw_ef_search: int,
    ) -> list[RetrievedChunkRow]:
        # Both settings are transaction-local. Older pgvector versions simply ignore
        # iterative_scan, while supported versions keep filtered ANN ordering strict.
        self._session.execute(
            text("SELECT set_config('hnsw.ef_search', :value, true)"),
            {"value": str(hnsw_ef_search)},
        )
        self._session.execute(
            text("SELECT set_config('hnsw.iterative_scan', 'strict_order', true)")
        )
        distance = DocumentEmbeddingRecord.embedding.op("<=>", return_type=Float)(
            query_vector
        ).label("distance")
        rows = self._session.execute(
            select(DocumentEmbeddingRecord, DocumentChunkRecord, DocumentRecord, distance)
            .join(DocumentChunkRecord, DocumentEmbeddingRecord.chunk_id == DocumentChunkRecord.id)
            .join(DocumentRecord, DocumentEmbeddingRecord.document_id == DocumentRecord.id)
            .where(*filters)
            .order_by(distance, DocumentChunkRecord.chunk_index, DocumentChunkRecord.id)
            .limit(limit)
        )
        return [
            self._row_from_records(embedding, chunk, document, float(row_distance))
            for embedding, chunk, document, row_distance in rows
        ]

    def _search_sqlite(
        self, *, filters: list[object], query_vector: list[float], limit: int
    ) -> list[RetrievedChunkRow]:
        # SQLite is test-only; SQL still applies every security/model filter before
        # deterministic cosine ranking is calculated in-process.
        rows = self._session.execute(
            select(DocumentEmbeddingRecord, DocumentChunkRecord, DocumentRecord)
            .join(DocumentChunkRecord, DocumentEmbeddingRecord.chunk_id == DocumentChunkRecord.id)
            .join(DocumentRecord, DocumentEmbeddingRecord.document_id == DocumentRecord.id)
            .where(*filters)
        )
        ranked = [
            self._row_from_records(
                embedding, chunk, document, _cosine_distance(query_vector, embedding.embedding)
            )
            for embedding, chunk, document in rows
        ]
        return sorted(ranked, key=lambda row: (row.distance, row.chunk_index, row.chunk_id))[:limit]

    @staticmethod
    def _row_from_records(
        embedding: DocumentEmbeddingRecord,
        chunk: DocumentChunkRecord,
        document: DocumentRecord,
        distance: float,
    ) -> RetrievedChunkRow:
        return RetrievedChunkRow(
            chunk_id=chunk.id,
            document_id=embedding.document_id,
            filename=document.original_filename,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            distance=distance,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section=chunk.section,
            heading=chunk.heading,
            source_block_start=chunk.source_block_start,
            source_block_end=chunk.source_block_end,
        )


def _cosine_distance(first: list[float], second: list[float]) -> float:
    numerator = sum(left * right for left, right in zip(first, second, strict=True))
    denominator = sqrt(sum(value * value for value in first)) * sqrt(
        sum(value * value for value in second)
    )
    return 1.0 if denominator == 0 else 1.0 - numerator / denominator
