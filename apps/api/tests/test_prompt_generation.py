from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from prompt_engine.compiler import GenericPromptCompiler
from prompt_engine.gaps import GapAnalyzer
from prompt_engine.intent import IntentAnalyzer, StructuredAnalysisRequest
from prompt_engine.schemas import PromptSpec

from app.api.v1.dependencies import get_prompt_generation_service
from app.main import app
from app.repositories.documents import DocumentNotFoundError
from app.services.context import ContextBuilder
from app.services.prompt_generation import PromptGenerationService
from app.services.retrieval import RetrievalDocumentNotReadyError, RetrievedChunk


@dataclass
class FakeStructuredAnalysisBackend:
    result: object | None = None
    error: Exception | None = None
    calls: int = 0
    request: StructuredAnalysisRequest | None = None

    def analyze(self, request: StructuredAnalysisRequest) -> object:
        self.calls += 1
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result


class TrackingCompiler(GenericPromptCompiler):
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, prompt_spec: PromptSpec) -> str:
        self.calls += 1
        return super().compile(prompt_spec)


def make_service(
    backend: FakeStructuredAnalysisBackend,
    compiler: TrackingCompiler,
    retrieval_service: object | None = None,
    context_builder: object | None = None,
) -> PromptGenerationService:
    return PromptGenerationService(
        intent_analyzer=IntentAnalyzer(backend),
        gap_analyzer=GapAnalyzer(),
        compiler=compiler,
        retrieval_service=retrieval_service,  # type: ignore[arg-type]
        context_builder=context_builder,  # type: ignore[arg-type]
    )


class FakeDocumentRetrieval:
    def __init__(
        self, results: list[RetrievedChunk] | None = None, error: Exception | None = None
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0
        self.arguments: dict[str, object] = {}

    def search(self, **kwargs: object) -> list[RetrievedChunk]:
        self.calls += 1
        self.arguments = kwargs
        if self.error is not None:
            raise self.error
        return self.results


class CountingContextBuilder:
    def __init__(self) -> None:
        self.builder = ContextBuilder(max_tokens=500)
        self.calls = 0

    def build(self, results: list[RetrievedChunk]):
        self.calls += 1
        return self.builder.build(results)


def _document_chunk(text: str = "The final examination is closed-book.") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        document_id="syllabus-1",
        filename="syllabus.pdf",
        chunk_index=0,
        text=text,
        distance=0.1,
        similarity=0.9,
        page_start=1,
        page_end=1,
        section="Assessment",
        heading="Final examination",
        source_block_start=1,
        source_block_end=1,
    )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("language", "objective"),
    [
        ("tr", "Müşteriye proje güncellemesi yaz."),
        ("en", "Write a project update for the customer."),
    ],
)
def test_ready_flow_uses_one_backend_call_and_compiles(
    client: TestClient, language: str, objective: str
) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={"task": {"type": "writing.email", "objective": objective}, "language": language}
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post(
        "/api/v1/prompts/generate", json={"input": objective, "language": language}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    assert response.json()["compiledPrompt"] is not None
    assert response.json()["promptSpec"]["language"] == language
    assert backend.calls == 1
    assert compiler.calls == 1
    assert backend.request is not None
    assert backend.request.document_context is None
    assert backend.request.document_context_requested is False


def test_document_aware_generation_scopes_retrieval_and_compiles_bounded_context(
    client: TestClient,
) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={
            "task": {"type": "writing.email", "objective": "Ask about the exam rule."},
            "language": "en",
        }
    )
    compiler = TrackingCompiler()
    retrieval = FakeDocumentRetrieval([_document_chunk()])
    context = CountingContextBuilder()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler, retrieval, context
    )

    response = client.post(
        "/api/v1/prompts/generate",
        json={
            "input": "Ask my teacher about the final exam rule.",
            "language": "en",
            "documentIds": ["syllabus-1"],
        },
    )

    assert response.status_code == 200
    assert retrieval.arguments["document_ids"] == ("syllabus-1",)
    assert (retrieval.calls, context.calls, backend.calls, compiler.calls) == (1, 1, 1, 1)
    assert backend.request is not None
    assert "The final examination is closed-book." in (backend.request.document_context or "")
    assert "untrusted reference data" in backend.request.instructions
    assert response.json()["promptSpec"]["sources"]["context"][0]["documentId"] == "syllabus-1"
    assert "SOURCE CONTEXT" in response.json()["compiledPrompt"]


def test_document_aware_generation_does_not_assert_unsupported_document_facts(
    client: TestClient,
) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={
            "task": {"type": "writing.email", "objective": "Ask about the final exam rule."},
            "language": "en",
            "missingInformation": [
                {"field": "exam_rule", "importance": "helpful", "question": "Which rule?"}
            ],
        }
    )
    compiler = TrackingCompiler()
    retrieval = FakeDocumentRetrieval([])
    context = CountingContextBuilder()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler, retrieval, context
    )

    response = client.post(
        "/api/v1/prompts/generate",
        json={
            "input": "Ask about the final exam.",
            "language": "en",
            "documentIds": ["syllabus-1"],
        },
    )

    assert response.status_code == 200
    assert backend.request is not None
    assert backend.request.document_context is None
    assert backend.request.document_context_requested is True
    assert "do not assert a fact" in backend.request.instructions
    assert response.json()["promptSpec"].get("sources") is None
    assert "SOURCE CONTEXT" not in response.json()["compiledPrompt"]


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (DocumentNotFoundError("outside workspace"), 404, "document_not_found"),
        (RetrievalDocumentNotReadyError("not embedded"), 409, "retrieval_document_not_ready"),
    ],
)
def test_document_aware_generation_validates_document_scope_and_readiness(
    client: TestClient, error: Exception, status_code: int, code: str
) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={"task": {"type": "general", "objective": "Help."}, "language": "en"}
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler, FakeDocumentRetrieval(error=error), CountingContextBuilder()
    )

    response = client.post(
        "/api/v1/prompts/generate",
        json={"input": "Use my document.", "language": "en", "documentIds": ["document-1"]},
    )

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert backend.calls == 0


def test_required_clarification_does_not_compile(client: TestClient) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={
            "task": {"type": "writing", "objective": "Write an update."},
            "language": "en",
            "missingInformation": [
                {"field": "audience", "importance": "required", "question": "Who is it for?"}
            ],
        }
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post(
        "/api/v1/prompts/generate", json={"input": "Write an update.", "language": "en"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "clarification_required"
    assert response.json()["compiledPrompt"] is None
    assert response.json()["clarificationPlan"]["shouldClarify"] is True
    assert compiler.calls == 0


def test_helpful_gap_does_not_block_compilation(client: TestClient) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={
            "task": {"type": "writing", "objective": "Write an update."},
            "language": "en",
            "missingInformation": [
                {"field": "tone", "importance": "helpful", "question": "Which tone?"}
            ],
        }
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post(
        "/api/v1/prompts/generate", json={"input": "Write an update.", "language": "en"}
    )

    assert response.status_code == 200
    assert response.json()["state"] == "ready"
    assert response.json()["clarificationPlan"]["shouldClarify"] is True
    assert compiler.calls == 1


def test_preset_hint_reaches_analysis_without_overwriting_explicit_intent(
    client: TestClient,
) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={
            "task": {"type": "research.compare", "objective": "Compare the two options."},
            "language": "en",
        }
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post(
        "/api/v1/prompts/generate",
        json={"input": "Compare two vendors.", "language": "en", "presetId": "write-email"},
    )

    assert response.status_code == 200
    assert backend.calls == 1
    assert backend.request is not None
    assert backend.request.preset is not None
    assert backend.request.preset.id == "write-email"
    assert response.json()["promptSpec"]["task"]["type"] == "research.compare"


def test_unknown_preset_is_rejected_cleanly(client: TestClient) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={"task": {"type": "general", "objective": "Help."}, "language": "en"}
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post(
        "/api/v1/prompts/generate",
        json={"input": "Help.", "language": "en", "presetId": "not-a-preset"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert backend.calls == 0


def test_invalid_input_has_a_stable_error(client: TestClient) -> None:
    response = client.post("/api/v1/prompts/generate", json={"input": "", "language": "en"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "invalid_request", "message": "Request data is invalid."}
    }


def test_provider_failure_does_not_leak_details(client: TestClient) -> None:
    backend = FakeStructuredAnalysisBackend(error=RuntimeError("provider secret failure"))
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post("/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "analysis_unavailable",
            "message": "Prompt analysis is temporarily unavailable.",
            "details": None,
        }
    }
    assert "provider secret failure" not in response.text


def test_invalid_structured_provider_output_is_mapped(client: TestClient) -> None:
    backend = FakeStructuredAnalysisBackend(
        result={"task": {"type": "general", "objective": "Help me."}, "language": "de"}
    )
    compiler = TrackingCompiler()
    app.dependency_overrides[get_prompt_generation_service] = lambda: make_service(
        backend, compiler
    )

    response = client.post("/api/v1/prompts/generate", json={"input": "Help me.", "language": "en"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_analysis_output"
