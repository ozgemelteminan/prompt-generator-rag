"""OpenAI Responses API adapter for structured PromptSpec analysis."""

from openai import OpenAI
from prompt_engine.intent import StructuredAnalysisRequest


class OpenAIResponsesStructuredAnalysisBackend:
    """Adapt the OpenAI Responses API to the provider-neutral analysis boundary."""

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

    def analyze(self, request: StructuredAnalysisRequest) -> object:
        """Make one Structured Outputs request and return its parsed Pydantic result."""
        preset_hint = ""
        if request.preset is not None:
            preset_hint = (
                "\n\nOptional quick-start preset (defaults only; user input takes priority):\n"
                f"- Task type hint: {request.preset.task_type_hint}\n"
                f"- Output format hint: {request.preset.output_format_hint or 'none'}"
            )
        response = self._client.responses.parse(
            model=self._model,
            instructions=request.instructions,
            input=(
                f"Selected output language: {request.input.language}\n\n"
                f"User request:\n{request.input.raw_request}{preset_hint}"
            ),
            text_format=request.response_schema,
            store=False,
        )
        if response.output_parsed is None:
            raise RuntimeError("OpenAI returned no structured analysis output.")
        return response.output_parsed
