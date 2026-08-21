from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from prompt_engine.compiler import GenericPromptCompiler
from prompt_engine.gaps import GapAnalyzer
from prompt_engine.intent import IntentAnalysisInput, IntentAnalyzer, StructuredAnalysisRequest
from prompt_engine.schemas import PromptSpec

from app.api.v1.dependencies import get_prompt_generation_service
from app.infrastructure.openai_analysis import OpenAIResponsesStructuredAnalysisBackend
from app.main import app
from app.services.prompt_generation import PromptGenerationService


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


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.output)


class FakeOpenAIClient:
    def __init__(self, output: object) -> None:
        self.responses = FakeResponses(output)


def make_service(
    backend: FakeStructuredAnalysisBackend, compiler: TrackingCompiler
) -> PromptGenerationService:
    return PromptGenerationService(
        intent_analyzer=IntentAnalyzer(backend),
        gap_analyzer=GapAnalyzer(),
        compiler=compiler,
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


def test_openai_adapter_uses_one_responses_structured_output_request() -> None:
    fake_client = FakeOpenAIClient(
        {"task": {"type": "general", "objective": "Help me."}, "language": "en"}
    )
    backend = OpenAIResponsesStructuredAnalysisBackend(
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        client=cast(OpenAI, fake_client),
    )
    result = backend.analyze(
        StructuredAnalysisRequest(input=IntentAnalysisInput(raw_request="Help me.", language="en"))
    )

    assert result == {"task": {"type": "general", "objective": "Help me."}, "language": "en"}
    assert len(fake_client.responses.calls) == 1
    assert fake_client.responses.calls[0]["text_format"].__name__ == "PromptSpec"
    assert fake_client.responses.calls[0]["store"] is False


def test_openai_adapter_includes_preset_as_a_default_hint() -> None:
    fake_client = FakeOpenAIClient(
        {"task": {"type": "general", "objective": "Help me."}, "language": "en"}
    )
    backend = OpenAIResponsesStructuredAnalysisBackend(
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        client=cast(OpenAI, fake_client),
    )

    from prompt_engine.presets import get_task_preset

    backend.analyze(
        StructuredAnalysisRequest(
            input=IntentAnalysisInput(raw_request="Help me.", language="en"),
            preset=get_task_preset("write-email"),
        )
    )

    assert "Optional quick-start preset" in str(fake_client.responses.calls[0]["input"])
    assert "writing.email" in str(fake_client.responses.calls[0]["input"])
