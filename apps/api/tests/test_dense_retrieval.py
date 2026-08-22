from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Float, create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import get_dense_retrieval_service
from app.core.caller import CallerContext
from app.db.models import Base, DocumentChunkRecord, DocumentEmbeddingRecord, DocumentRecord
from app.infrastructure.huggingface_embeddings import (
    E5_RETRIEVAL_INSTRUCTION,
    SELECTED_EMBEDDING_DIMENSION,
    MultilingualE5EmbeddingProvider,
)
from app.main import app
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import DenseRetrievalRepository
from app.services.embeddings import EmbeddingProviderError
from app.services.retrieval import DenseRetrievalService


class FakeQueryEmbeddingProvider:
    model_id = "intfloat/multilingual-e5-large-instruct"
    dimension = SELECTED_EMBEDDING_DIMENSION

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.fail:
            raise EmbeddingProviderError("provider internals")
        return [1.0] + [0.0] * (self.dimension - 1)

    def embed_passages(self, _: list[str]) -> list[list[float]]:
        raise AssertionError("Search must only embed the query.")


def _service() -> tuple[DenseRetrievalService, Session, FakeQueryEmbeddingProvider]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    provider = FakeQueryEmbeddingProvider()
    return (
        DenseRetrievalService(
            caller=CallerContext("workspace-a"),
            document_repository=DocumentRepository(session),
            retrieval_repository=DenseRetrievalRepository(session),
            embedding_provider=provider,
            default_limit=2,
            max_limit=3,
            expected_dimension=SELECTED_EMBEDDING_DIMENSION,
            hnsw_ef_search=100,
        ),
        session,
        provider,
    )


def _add_embedding(
    session: Session,
    *,
    workspace_id: str,
    document_id: str | None = None,
    chunk_index: int = 0,
    vector: list[float] | None = None,
    model_id: str = "intfloat/multilingual-e5-large-instruct",
    status: str = "embedded",
) -> str:
    document_id = document_id or str(uuid4())
    chunk_id = str(uuid4())
    session.add(
        DocumentRecord(
            id=document_id,
            workspace_id=workspace_id,
            original_filename=f"{document_id}.txt",
            media_type="text/plain",
            file_size=10,
            checksum=str(uuid4()).replace("-", ""),
            ingestion_status=status,
            storage_key=f"{workspace_id}/{document_id}",
        )
    )
    session.add(
        DocumentChunkRecord(
            id=chunk_id,
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_index=chunk_index,
            text=f"chunk {chunk_index} in {workspace_id}",
            token_count=2,
            language="en",
            page_start=1,
            page_end=1,
            section="Section",
            heading="Heading",
            source_block_start=chunk_index,
            source_block_end=chunk_index,
        )
    )
    if vector is not None:
        session.add(
            DocumentEmbeddingRecord(
                id=str(uuid4()),
                workspace_id=workspace_id,
                document_id=document_id,
                chunk_id=chunk_id,
                embedding=vector,
                embedding_model_id=model_id,
                embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
            )
        )
    session.commit()
    return document_id


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_dense_search_is_ranked_workspace_scoped_and_returns_source_metadata(
    client: TestClient,
) -> None:
    service, session, provider = _service()
    app.dependency_overrides[get_dense_retrieval_service] = lambda: service
    first = _add_embedding(
        session, workspace_id="workspace-a", chunk_index=1, vector=[1.0] + [0.0] * 1023
    )
    _add_embedding(
        session, workspace_id="workspace-a", chunk_index=0, vector=[0.0, 1.0] + [0.0] * 1022
    )
    _add_embedding(session, workspace_id="workspace-b", vector=[1.0] + [0.0] * 1023)
    _add_embedding(
        session, workspace_id="workspace-a", vector=[1.0] + [0.0] * 1023, model_id="other"
    )

    response = client.post("/api/v1/retrieval/search", json={"query": "  relevant request  "})

    assert response.status_code == 200
    payload = response.json()["results"]
    assert provider.calls == ["relevant request"]
    assert [item["documentId"] for item in payload] == [first, payload[1]["documentId"]]
    assert payload[0]["distance"] == 0.0
    assert payload[0]["similarity"] == 1.0
    assert payload[0]["pageStart"] == payload[0]["pageEnd"] == 1
    assert payload[0]["sourceBlockStart"] == payload[0]["sourceBlockEnd"] == 1
    assert all("embedding" not in item for item in payload)
    assert all(item["text"].endswith("workspace-a") for item in payload)


def test_dense_search_validates_limits_and_document_scope(client: TestClient) -> None:
    service, session, _ = _service()
    app.dependency_overrides[get_dense_retrieval_service] = lambda: service
    ready = _add_embedding(session, workspace_id="workspace-a", vector=[1.0] + [0.0] * 1023)
    unembedded = _add_embedding(session, workspace_id="workspace-a", status="chunked")
    foreign = _add_embedding(session, workspace_id="workspace-b", vector=[1.0] + [0.0] * 1023)

    assert client.post("/api/v1/retrieval/search", json={"query": " "}).status_code == 422
    assert (
        client.post("/api/v1/retrieval/search", json={"query": "x", "limit": 4}).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/retrieval/search", json={"query": "x", "documentIds": [unembedded]}
        ).json()["error"]["code"]
        == "retrieval_document_not_ready"
    )
    assert (
        client.post(
            "/api/v1/retrieval/search", json={"query": "x", "documentIds": [foreign]}
        ).status_code
        == 404
    )
    scoped = client.post("/api/v1/retrieval/search", json={"query": "x", "documentIds": [ready]})
    assert scoped.status_code == 200
    assert [item["documentId"] for item in scoped.json()["results"]] == [ready]


def test_e5_query_format_and_safe_provider_failure(client: TestClient) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.text: str | None = None
            self.kwargs: dict[str, object] | None = None

        def encode(self, text: str, **kwargs: object) -> object:
            self.text = text
            self.kwargs = kwargs

            class Vector:
                def tolist(self) -> list[float]:
                    return [1.0] * SELECTED_EMBEDDING_DIMENSION

            return Vector()

        def get_embedding_dimension(self) -> int:
            return SELECTED_EMBEDDING_DIMENSION

    adapter = MultilingualE5EmbeddingProvider(
        model_id="intfloat/multilingual-e5-large-instruct", batch_size=8
    )
    model = FakeModel()
    adapter._model = model
    assert len(adapter.embed_query("soru")) == SELECTED_EMBEDDING_DIMENSION
    assert model.text == f"Instruct: {E5_RETRIEVAL_INSTRUCTION}\nQuery: soru"
    assert model.kwargs == {"normalize_embeddings": True, "show_progress_bar": False}

    service, _, provider = _service()
    provider.fail = True
    app.dependency_overrides[get_dense_retrieval_service] = lambda: service
    response = client.post("/api/v1/retrieval/search", json={"query": "safe"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "retrieval_failed"


def test_postgres_cosine_distance_expression_is_scalar_float() -> None:
    class CapturingSession:
        def __init__(self) -> None:
            self.statements: list[object] = []

        def execute(self, statement: object, *_: object) -> list[object]:
            self.statements.append(statement)
            return []

    session = CapturingSession()
    DenseRetrievalRepository(session)._search_postgres(  # type: ignore[arg-type]
        filters=[],
        query_vector=[1.0] * SELECTED_EMBEDDING_DIMENSION,
        limit=5,
        hnsw_ef_search=100,
    )

    statement = session.statements[-1]
    distance = tuple(statement.selected_columns)[-1]  # type: ignore[union-attr]
    assert isinstance(distance.type, Float)
    assert "<=>" in str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[union-attr]
