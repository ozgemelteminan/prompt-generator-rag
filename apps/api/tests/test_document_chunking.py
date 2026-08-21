import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.dependencies import get_document_service
from app.core.caller import CallerContext
from app.db.models import Base, DocumentChunkRecord, DocumentRecord
from app.document_processing.chunking import StructureAwareChunker, Tokenizer
from app.document_processing.models import ChunkingConfig, TextBlock
from app.infrastructure.local_document_storage import LocalDocumentStorage
from app.main import app
from app.repositories.documents import DocumentRepository
from app.services.documents import DocumentService


def _chunker(
    *, target: int = 12, maximum: int | None = None, overlap: int = 0
) -> StructureAwareChunker:
    return StructureAwareChunker(ChunkingConfig(target, maximum or max(target, 16), overlap))


def _blocks(*items: tuple[str, str, int | None, str | None]) -> tuple[TextBlock, ...]:
    return tuple(
        TextBlock(block_type, text, index, page_number=page, section=section)
        for index, (block_type, text, page, section) in enumerate(items)
    )


def test_same_section_paragraphs_combine_but_heading_changes_do_not_merge() -> None:
    blocks = _blocks(
        ("heading", "First", None, None),
        ("paragraph", "One two three.", None, "First"),
        ("paragraph", "Four five six.", None, "First"),
        ("heading", "Second", None, None),
        ("paragraph", "Seven eight nine.", None, "Second"),
    )

    chunks = _chunker(target=20).chunk(
        document_id="document", workspace_id="workspace", language="en", blocks=blocks
    )

    assert len(chunks) == 2
    assert "One two three." in chunks[0].text and "Four five six." in chunks[0].text
    assert chunks[0].heading == "First"
    assert chunks[1].heading == "Second"
    assert "Seven eight nine." in chunks[1].text


def test_large_paragraph_uses_sentences_then_token_fallback_within_limit() -> None:
    sentence = " ".join(f"word{index}" for index in range(20))
    blocks = _blocks(("paragraph", f"One two three. {sentence}.", None, None))
    tokenizer = Tokenizer()

    chunks = _chunker(target=7, maximum=8).chunk(
        document_id="document", workspace_id="workspace", language="en", blocks=blocks
    )

    assert all(chunk.token_count <= 8 for chunk in chunks)
    assert chunks[0].text == "One two three."
    assert any("word0" in chunk.text for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(tokenizer.count(chunk.text) == chunk.token_count for chunk in chunks)


def test_metadata_preserves_pages_context_source_range_and_language() -> None:
    blocks = _blocks(
        ("heading", "Bölüm", 1, None),
        ("paragraph", "Türkçe içerik burada.", 1, "Bölüm"),
        ("paragraph", "İkinci sayfa devam eder.", 2, "Bölüm"),
    )

    chunk = _chunker(target=30).chunk(
        document_id="document", workspace_id="workspace", language="tr", blocks=blocks
    )[0]

    assert chunk.workspace_id == "workspace"
    assert chunk.language == "tr"
    assert chunk.section == chunk.heading == "Bölüm"
    assert (chunk.page_start, chunk.page_end) == (1, 2)
    assert (chunk.source_block_start, chunk.source_block_end) == (0, 2)


def test_overlap_is_deterministic_context_local_and_can_be_disabled() -> None:
    blocks = _blocks(
        ("heading", "Same", None, None),
        ("paragraph", "one two three.", None, "Same"),
        ("paragraph", "four five six.", None, "Same"),
        ("paragraph", "seven eight nine.", None, "Same"),
        ("heading", "Other", None, None),
        ("paragraph", "ten eleven twelve.", None, "Other"),
    )
    with_overlap = _chunker(target=10, maximum=14, overlap=4).chunk(
        document_id="document", workspace_id="workspace", language="en", blocks=blocks
    )
    without_overlap = _chunker(target=10, maximum=14).chunk(
        document_id="document", workspace_id="workspace", language="en", blocks=blocks
    )

    assert with_overlap == _chunker(target=10, maximum=14, overlap=4).chunk(
        document_id="document", workspace_id="workspace", language="en", blocks=blocks
    )
    assert "four five six." in with_overlap[1].text
    assert "four five six." not in without_overlap[1].text
    assert all(chunk.token_count <= 14 for chunk in with_overlap)
    assert all(chunk.heading == "Other" for chunk in with_overlap if "ten eleven" in chunk.text)


def test_non_page_blocks_leave_page_metadata_null() -> None:
    chunk = _chunker().chunk(
        document_id="document",
        workspace_id="workspace",
        language="en",
        blocks=_blocks(("paragraph", "plain text only", None, None)),
    )[0]
    assert chunk.page_start is None and chunk.page_end is None


def _service(tmp_path, workspace_id: str = "workspace-a") -> tuple[DocumentService, Session]:
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
            chunker=_chunker(target=8, maximum=12, overlap=2),
        ),
        session,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_chunk_service_persists_replaces_and_returns_statistics(
    tmp_path, client: TestClient
) -> None:
    service, session = _service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service
    upload = client.post(
        "/api/v1/documents", files={"file": ("notes.txt", b"One two three.\n\nFour five six.")}
    )
    document_id = upload.json()["id"]
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 200

    first = client.post(f"/api/v1/documents/{document_id}/chunk")
    second = client.post(f"/api/v1/documents/{document_id}/chunk")

    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "chunked"
    assert second.json()["chunkCount"] == 1
    rows = list(
        session.scalars(select(DocumentChunkRecord).order_by(DocumentChunkRecord.chunk_index))
    )
    assert len(rows) == 1
    assert rows[0].workspace_id == "workspace-a"
    assert rows[0].token_count <= 12


def test_chunking_requires_parsed_document_and_respects_workspace(
    tmp_path, client: TestClient
) -> None:
    service_a, session = _service(tmp_path, "workspace-a")
    service_b = DocumentService(
        caller=CallerContext("workspace-b"),
        repository=DocumentRepository(session),
        storage=LocalDocumentStorage(tmp_path / "uploads"),
        max_upload_bytes=10_000,
        chunker=_chunker(),
    )
    current = service_a
    app.dependency_overrides[get_document_service] = lambda: current
    upload = client.post("/api/v1/documents", files={"file": ("notes.txt", b"safe text")})
    document_id = upload.json()["id"]

    assert client.post(f"/api/v1/documents/{document_id}/chunk").status_code == 409
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 200
    current = service_b
    assert client.post(f"/api/v1/documents/{document_id}/chunk").status_code == 404
    assert session.get(DocumentRecord, document_id).ingestion_status == "parsed"


def test_chunking_failure_marks_document_failed_without_partial_chunks(
    tmp_path, client: TestClient
) -> None:
    service, session = _service(tmp_path)
    app.dependency_overrides[get_document_service] = lambda: service
    upload = client.post("/api/v1/documents", files={"file": ("notes.txt", b"safe text")})
    document_id = upload.json()["id"]
    assert client.post(f"/api/v1/documents/{document_id}/process").status_code == 200

    class FailingChunker:
        def chunk(self, **_: object) -> tuple[object, ...]:
            raise RuntimeError("internal failure")

        def statistics(self, _: tuple[object, ...]) -> object:
            raise AssertionError("Statistics should not be called")

    service._chunker = FailingChunker()  # type: ignore[assignment]
    response = client.post(f"/api/v1/documents/{document_id}/chunk")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "document_chunking_failed"
    assert session.get(DocumentRecord, document_id).ingestion_status == "failed"
    assert list(session.scalars(select(DocumentChunkRecord))) == []
