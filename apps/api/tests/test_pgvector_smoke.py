"""Opt-in PostgreSQL + pgvector production-repository smoke test.

Run only against an isolated database that has already received ``alembic upgrade
head``. It deliberately has no SQLite fallback: this verifies the real pgvector
cosine/HNSW path.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.db.models import DocumentChunkRecord, DocumentEmbeddingRecord, DocumentRecord
from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION
from app.repositories.retrieval import DenseRetrievalRepository

SMOKE_DATABASE_URL = os.environ.get("PGVECTOR_SMOKE_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_PGVECTOR_SMOKE") != "1" or not SMOKE_DATABASE_URL,
    reason="Set RUN_PGVECTOR_SMOKE=1 and PGVECTOR_SMOKE_DATABASE_URL for pgvector smoke.",
)


def _vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (SELECTED_EMBEDDING_DIMENSION - 2)


def _add_document_with_embedding(
    session: Session,
    *,
    workspace_id: str,
    document_id: str,
    chunk_id: str,
    vector: list[float],
) -> None:
    session.add(
        DocumentRecord(
            id=document_id,
            workspace_id=workspace_id,
            original_filename=f"{document_id}.txt",
            media_type="text/plain",
            file_size=12,
            checksum=uuid4().hex,
            ingestion_status="embedded",
            storage_key=f"m6-smoke/{document_id}",
        )
    )
    session.add(
        DocumentChunkRecord(
            id=chunk_id,
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_index=0,
            text=f"M6 smoke chunk for {workspace_id}",
            token_count=5,
            language="en",
            page_start=1,
            page_end=1,
            section="Smoke",
            heading="Parity",
            source_block_start=0,
            source_block_end=0,
        )
    )
    session.add(
        DocumentEmbeddingRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_id=chunk_id,
            embedding=vector,
            embedding_model_id="intfloat/multilingual-e5-large-instruct",
            embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
        )
    )


def test_pgvector_hnsw_cosine_retrieval_is_workspace_and_document_scoped() -> None:
    assert SMOKE_DATABASE_URL is not None
    engine = create_engine(SMOKE_DATABASE_URL, pool_pre_ping=True)
    assert engine.dialect.name == "postgresql", "PGVECTOR_SMOKE_DATABASE_URL must be PostgreSQL."
    session = Session(engine)
    transaction = session.begin()
    try:
        assert (
            session.scalar(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
            == "vector"
        )
        assert (
            session.scalar(text("SELECT to_regclass('public.document_embeddings')"))
            == "document_embeddings"
        )
        assert (
            session.scalar(
                text("SELECT to_regclass('public.ix_document_embeddings_embedding_hnsw')")
            )
            == "ix_document_embeddings_embedding_hnsw"
        )
        workspace_a = f"m6-workspace-a-{uuid4()}"
        workspace_b = f"m6-workspace-b-{uuid4()}"
        document_a = str(uuid4())
        document_b = str(uuid4())
        chunk_a = str(uuid4())
        chunk_b = str(uuid4())
        _add_document_with_embedding(
            session,
            workspace_id=workspace_a,
            document_id=document_a,
            chunk_id=chunk_a,
            vector=_vector(1.0),
        )
        _add_document_with_embedding(
            session,
            workspace_id=workspace_b,
            document_id=document_b,
            chunk_id=chunk_b,
            vector=_vector(1.0),
        )
        session.flush()

        repository = DenseRetrievalRepository(session)
        results = repository.search(
            workspace_id=workspace_a,
            query_vector=_vector(1.0),
            model_id="intfloat/multilingual-e5-large-instruct",
            dimension=SELECTED_EMBEDDING_DIMENSION,
            limit=5,
            hnsw_ef_search=100,
        )
        assert [result.document_id for result in results] == [document_a]
        assert results[0].chunk_id == chunk_a

        document_filtered = repository.search(
            workspace_id=workspace_a,
            query_vector=_vector(1.0),
            model_id="intfloat/multilingual-e5-large-instruct",
            dimension=SELECTED_EMBEDDING_DIMENSION,
            limit=5,
            document_ids=(document_a,),
            hnsw_ef_search=100,
        )
        assert [result.document_id for result in document_filtered] == [document_a]
        assert (
            repository.search(
                workspace_id=workspace_a,
                query_vector=_vector(1.0),
                model_id="intfloat/multilingual-e5-large-instruct",
                dimension=SELECTED_EMBEDDING_DIMENSION,
                limit=5,
                document_ids=(document_b,),
                hnsw_ef_search=100,
            )
            == []
        )
    finally:
        transaction.rollback()
        session.close()
        engine.dispose()
