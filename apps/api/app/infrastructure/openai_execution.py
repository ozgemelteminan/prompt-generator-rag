"""OpenAI Responses API adapter for plain-text prompt execution."""

from openai import OpenAI
from prompt_engine.execution import ExecutionResult


class OpenAIResponsesExecutionBackend:
    """Adapt OpenAI text generation to the provider-neutral execution boundary."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        client: OpenAI | None = None,
    ) -> None:
        self._client = client or OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self._model = model

    def execute(self, compiled_prompt: str) -> ExecutionResult:
        response = self._client.responses.create(
            model=self._model,
            input=compiled_prompt,
            store=False,
        )
        return ExecutionResult(output=response.output_text)
