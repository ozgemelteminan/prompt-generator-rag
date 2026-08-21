from dataclasses import dataclass
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient
from openai import OpenAI
from prompt_engine.execution import ExecutionResult

from app.api.v1.dependencies import get_prompt_execution_service, get_prompt_generation_service
from app.infrastructure.openai_execution import OpenAIResponsesExecutionBackend
from app.main import app
from app.services.prompt_execution import PromptExecutionService


@dataclass
class FakeExecutionBackend:
    output: str = "Generated answer."
    error: Exception | None = None
    calls: int = 0
    compiled_prompt: str | None = None

    def execute(self, compiled_prompt: str) -> ExecutionResult:
        self.calls += 1
        self.compiled_prompt = compiled_prompt
        if self.error is not None:
            raise self.error
        return ExecutionResult(output=self.output)


class FakeResponses:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output)


class FakeOpenAIClient:
    def __init__(self, output: str) -> None:
        self.responses = FakeResponses(output)


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def override_execution_service(
    backend: FakeExecutionBackend, *, max_characters: int = 20_000
) -> None:
    app.dependency_overrides[get_prompt_execution_service] = lambda: PromptExecutionService(
        backend=backend,
        max_input_characters=max_characters,
    )


@pytest.mark.parametrize(
    "compiled_prompt",
    [
        "Türkçe yanıt vererek bir proje güncellemesi yaz.",
        "Write a project update in English.",
    ],
)
def test_execute_returns_generated_text_with_one_backend_call(
    client: TestClient, compiled_prompt: str
) -> None:
    backend = FakeExecutionBackend(output="Model answer")
    override_execution_service(backend)

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": compiled_prompt})

    assert response.status_code == 200
    assert response.json() == {"output": "Model answer"}
    assert backend.calls == 1
    assert backend.compiled_prompt == compiled_prompt


def test_execute_does_not_request_prompt_generation_or_analysis(client: TestClient) -> None:
    backend = FakeExecutionBackend()
    override_execution_service(backend)

    def generation_service_must_not_be_requested() -> None:
        raise AssertionError("Execution must not request the generation workflow.")

    app.dependency_overrides[get_prompt_generation_service] = (
        generation_service_must_not_be_requested
    )

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": "Run this."})

    assert response.status_code == 200
    assert backend.calls == 1


@pytest.mark.parametrize("compiled_prompt", ["", "   \n\t "])
def test_execute_rejects_empty_or_whitespace_prompts(
    client: TestClient, compiled_prompt: str
) -> None:
    backend = FakeExecutionBackend()
    override_execution_service(backend)

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": compiled_prompt})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert backend.calls == 0


def test_execute_rejects_oversized_prompt(client: TestClient) -> None:
    backend = FakeExecutionBackend()
    override_execution_service(backend, max_characters=10)

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": "eleven chars"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert backend.calls == 0


def test_execute_provider_failure_is_stable_and_does_not_leak_details(client: TestClient) -> None:
    backend = FakeExecutionBackend(error=RuntimeError("provider secret failure"))
    override_execution_service(backend)

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": "Run this."})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "execution_unavailable"
    assert "provider secret failure" not in response.text


def test_execute_rejects_empty_provider_output(client: TestClient) -> None:
    backend = FakeExecutionBackend(output="  ")
    override_execution_service(backend)

    response = client.post("/api/v1/prompts/execute", json={"compiledPrompt": "Run this."})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "invalid_execution_output"


def test_openai_execution_adapter_uses_one_plain_responses_request() -> None:
    fake_client = FakeOpenAIClient("Generated answer")
    backend = OpenAIResponsesExecutionBackend(
        api_key="test-key",
        model="test-model",
        timeout_seconds=1,
        client=cast(OpenAI, fake_client),
    )

    result = backend.execute("Run this prompt.")

    assert result == ExecutionResult(output="Generated answer")
    assert len(fake_client.responses.calls) == 1
    assert fake_client.responses.calls[0] == {
        "model": "test-model",
        "input": "Run this prompt.",
        "store": False,
    }
