from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import get_document_service
from app.core.caller import CallerContext
from app.db.models import Base, DocumentRecord
from app.infrastructure.local_document_storage import DocumentStorageError, LocalDocumentStorage
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services.documents import DocumentService


def make_service(tmp_path, *, workspace_id: str = "workspace-a", max_bytes: int = 1_000):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    return DocumentService(
        caller=CallerContext(workspace_id),
        repository=DocumentRepository(session),
        storage=LocalDocumentStorage(tmp_path / "uploads"),
        max_upload_bytes=max_bytes,
    ), session


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_valid_text_upload_persists_metadata_and_keeps_storage_path_private(
    tmp_path, client: TestClient
) -> None:
    service, session = make_service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service

    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello document", "text/plain")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "notes.txt"
    assert payload["mediaType"] == "text/plain"
    assert payload["status"] == "uploaded"
    assert payload["size"] == len(b"hello document")
    assert "storage" not in payload
    record = session.get(DocumentRecord, payload["id"])
    assert record is not None
    assert record.storage_key.endswith("/original")


@pytest.mark.parametrize(
    ("filename", "content", "expected_code", "expected_status"),
    [
        ("empty.txt", b"", "document_empty", 422),
        ("image.png", b"\x89PNG\r\n\x1a\n", "document_unsupported_type", 415),
    ],
)
def test_invalid_uploads_are_rejected_safely(
    tmp_path,
    client: TestClient,
    filename: str,
    content: bytes,
    expected_code: str,
    expected_status: int,
) -> None:
    service, _ = make_service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service

    response = client.post("/api/v1/documents", files={"file": (filename, content)})

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


def test_oversized_upload_is_rejected_without_storage(tmp_path, client: TestClient) -> None:
    service, _ = make_service(tmp_path, max_bytes=3)
    app.dependency_overrides[get_document_service] = lambda: service

    response = client.post("/api/v1/documents", files={"file": ("notes.txt", b"four")})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"
    assert not (tmp_path / "uploads").exists()


def test_path_traversal_filename_is_metadata_only_and_sanitized(
    tmp_path, client: TestClient
) -> None:
    service, _ = make_service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service

    response = client.post(
        "/api/v1/documents", files={"file": ("../../private/notes.txt", b"safe text")}
    )

    assert response.status_code == 200
    assert response.json()["filename"] == "notes.txt"
    assert "../" not in response.text


def test_identical_content_deduplicates_per_workspace(tmp_path, client: TestClient) -> None:
    service, _ = make_service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service

    first = client.post("/api/v1/documents", files={"file": ("one.txt", b"same content")})
    second = client.post("/api/v1/documents", files={"file": ("two.txt", b"same content")})

    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["deduplicated"] is True
    assert first.json()["checksum"] == second.json()["checksum"]


def test_local_storage_reads_only_valid_internal_keys(tmp_path) -> None:
    storage = LocalDocumentStorage(tmp_path / "uploads")
    key = storage.save(workspace_id="workspace-a", document_id="document-a", content=b"original")

    assert storage.read(key) == b"original"
    with pytest.raises(DocumentStorageError):
        storage.read("../../outside")


def test_document_list_detail_and_delete_are_workspace_scoped(tmp_path, client: TestClient) -> None:
    service_a, session = make_service(tmp_path, workspace_id="workspace-a")
    service_b = DocumentService(
        caller=CallerContext("workspace-b"),
        repository=DocumentRepository(session),
        storage=LocalDocumentStorage(tmp_path / "uploads"),
        max_upload_bytes=1_000,
    )
    current = service_a
    app.dependency_overrides[get_document_service] = lambda: current

    created = client.post("/api/v1/documents", files={"file": ("notes.txt", b"workspace A")})
    document_id = created.json()["id"]
    assert client.get("/api/v1/documents").json()["items"][0]["id"] == document_id

    current = service_b
    assert client.get("/api/v1/documents").json()["items"] == []
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404

    current = service_a
    assert client.delete(f"/api/v1/documents/{document_id}").status_code == 204
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 404


@dataclass
class FailingStorage:
    def save(self, *, workspace_id: str, document_id: str, content: bytes) -> str:
        raise DocumentStorageError("/private/path must not leak")

    def delete(self, storage_key: str) -> None:
        raise AssertionError("Delete should not be called after failed save")

    def read(self, storage_key: str) -> bytes:
        raise AssertionError("Read is not used during upload")


def test_storage_failure_uses_stable_error_without_filesystem_details(
    tmp_path, client: TestClient
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = DocumentService(
        caller=CallerContext("workspace-a"),
        repository=DocumentRepository(Session(engine)),
        storage=FailingStorage(),
        max_upload_bytes=1_000,
    )
    app.dependency_overrides[get_document_service] = lambda: service

    response = client.post("/api/v1/documents", files={"file": ("notes.txt", b"text")})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "document_storage_failed"
    assert "/private/path" not in response.text
