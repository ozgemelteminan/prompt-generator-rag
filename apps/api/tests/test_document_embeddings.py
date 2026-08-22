from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pgvector.sqlalchemy import Vector as PostgreSQLVector
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import get_document_service
from app.core.caller import CallerContext
from app.db.models import Base, DocumentChunkRecord, DocumentEmbeddingRecord, DocumentRecord
from app.db.vector import PgVector
from app.document_processing.chunking import StructureAwareChunker
from app.document_processing.models import ChunkingConfig
from app.infrastructure.huggingface_embeddings import (
    SELECTED_EMBEDDING_DIMENSION,
    MultilingualE5EmbeddingProvider,
)
from app.infrastructure.local_document_storage import LocalDocumentStorage
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingProviderError


class FakeEmbeddingProvider:
    model_id = "intfloat/multilingual-e5-large-instruct"
    dimension = SELECTED_EMBEDDING_DIMENSION

    def __init__(self, *, fail: bool = False, dimension: int | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail
        if dimension is not None:
            self.dimension = dimension

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        if self.fail:
            raise EmbeddingProviderError("hidden provider failure")
        return [[float(index + 1)] * self.dimension for index, _ in enumerate(texts)]


def _service(
    tmp_path: Path,
    provider: FakeEmbeddingProvider,
    workspace_id: str = "workspace-a",
) -> tuple[DocumentService, Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    return (
        DocumentService(
            caller=CallerContext(workspace_id),
            repository=DocumentRepository(session),
            storage=LocalDocumentStorage(tmp_path / "uploads"),
            max_upload_bytes=10_000,
            chunker=StructureAwareChunker(
                ChunkingConfig(target_tokens=3, max_tokens=4, overlap_tokens=0)
            ),
            embedding_provider=provider,
            embedding_batch_size=1,
            embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
        ),
        session,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _chunked_document(client: TestClient) -> str:
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"One two three. Four five six. Seven eight nine.")},
    )
    document_id = upload.json()["id"]
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 200
    assert client.post(f"/api/v1/documents/{document_id}/chunk").status_code == 200
    return document_id


def test_embed_persists_batched_vectors_and_replaces_existing_rows(
    tmp_path: Path, client: TestClient
) -> None:
    provider = FakeEmbeddingProvider()
    service, session = _service(tmp_path, provider)
    app.dependency_overrides[get_document_service] = lambda: service
    document_id = _chunked_document(client)
    chunk_count = len(list(session.scalars(select(DocumentChunkRecord))))

    first = client.post(f"/api/v1/documents/{document_id}/embed")
    second = client.post(f"/api/v1/documents/{document_id}/embed")

    assert first.status_code == second.status_code == 200
    assert first.json() == {
        "documentId": document_id,
        "status": "embedded",
        "chunkCount": chunk_count,
        "embeddedChunkCount": chunk_count,
        "embeddingModel": provider.model_id,
    }
    rows = list(session.scalars(select(DocumentEmbeddingRecord)))
    assert len(rows) == chunk_count
    assert all(row.embedding_model_id == provider.model_id for row in rows)
    assert all(len(row.embedding) == SELECTED_EMBEDDING_DIMENSION for row in rows)
    assert len(provider.calls) == chunk_count * 2
    assert session.get(DocumentRecord, document_id).ingestion_status == "embedded"


def test_embedding_rejects_unchunked_and_other_workspace(
    tmp_path: Path, client: TestClient
) -> None:
    service_a, session = _service(tmp_path, FakeEmbeddingProvider())
    service_b, _ = _service(tmp_path, FakeEmbeddingProvider(), "workspace-b")
    current = service_a
    app.dependency_overrides[get_document_service] = lambda: current
    upload = client.post("/api/v1/documents", files={"file": ("notes.txt", b"safe text")})
    document_id = upload.json()["id"]
    assert client.post(f"/api/v1/documents/{document_id}/embed").status_code == 409
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 200
    assert client.post(f"/api/v1/documents/{document_id}/chunk").status_code == 200
    current = service_b
    assert client.post(f"/api/v1/documents/{document_id}/embed").status_code == 404
    assert session.get(DocumentRecord, document_id).ingestion_status == "chunked"


def test_embedding_failure_or_bad_dimension_never_marks_embedded(
    tmp_path: Path, client: TestClient
) -> None:
    provider = FakeEmbeddingProvider(fail=True)
    service, session = _service(tmp_path, provider)
    app.dependency_overrides[get_document_service] = lambda: service
    document_id = _chunked_document(client)

    failed = client.post(f"/api/v1/documents/{document_id}/embed")

    assert failed.status_code == 422
    assert failed.json()["error"]["code"] == "embedding_failed"
    assert session.get(DocumentRecord, document_id).ingestion_status == "failed"
    assert list(session.scalars(select(DocumentEmbeddingRecord))) == []


def test_embedding_rejects_invalid_dimension_before_persistence(
    tmp_path: Path, client: TestClient
) -> None:
    provider = FakeEmbeddingProvider(dimension=3)
    service, session = _service(tmp_path, provider)
    app.dependency_overrides[get_document_service] = lambda: service
    document_id = _chunked_document(client)

    response = client.post(f"/api/v1/documents/{document_id}/embed")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "embedding_dimension_mismatch"
    assert session.get(DocumentRecord, document_id).ingestion_status == "failed"
    assert list(session.scalars(select(DocumentEmbeddingRecord))) == []


def test_pgvector_postgres_dialect_adapts_with_dimension() -> None:
    vector = PgVector(SELECTED_EMBEDDING_DIMENSION)

    adapted = vector.dialect_impl(postgresql.dialect())

    assert isinstance(adapted.impl, PostgreSQLVector)
    assert adapted.compile(dialect=postgresql.dialect()) == "VECTOR(1024)"


def test_e5_provider_embeds_raw_passages_with_normalization() -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], dict[str, object]]] = []

        def get_embedding_dimension(self) -> int:
            return SELECTED_EMBEDDING_DIMENSION

        def encode(self, texts: list[str], **kwargs: object) -> object:
            self.calls.append((texts, kwargs))

            class Vectors:
                def tolist(self) -> list[list[float]]:
                    return [[0.25] * SELECTED_EMBEDDING_DIMENSION]

            return Vectors()

    provider = MultilingualE5EmbeddingProvider(
        model_id="intfloat/multilingual-e5-large-instruct", batch_size=8
    )
    fake_model = FakeModel()
    provider._model = fake_model

    assert provider.embed_passages(["raw passage text"])[0][0] == 0.25
    assert provider.dimension == SELECTED_EMBEDDING_DIMENSION
    assert fake_model.calls == [
        (
            ["raw passage text"],
            {"batch_size": 8, "normalize_embeddings": True, "show_progress_bar": False},
        )
    ]
