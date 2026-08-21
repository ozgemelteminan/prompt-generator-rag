"""Application service for direct execution of an already compiled prompt."""

from dataclasses import dataclass

from prompt_engine.errors import (
    ExecutionBackendError,
    InvalidExecutionOutputError,
    InvalidExecutionRequestError,
)
from prompt_engine.execution import ExecutionBackend

from app.repositories.prompt_history import PromptHistoryRepository, PromptRecordNotFoundError
from app.services.usage import UsageAction, UsageGuard


@dataclass(frozen=True)
class PromptExecutionOutcome:
    output: str
    execution_id: str | None


class PromptExecutionService:
    """Validate and delegate one explicit compiled-prompt execution."""

    def __init__(
        self,
        *,
        backend: ExecutionBackend,
        max_input_characters: int,
        history_repository: PromptHistoryRepository | None = None,
        usage_guard: UsageGuard | None = None,
    ) -> None:
        self._backend = backend
        self._max_input_characters = max_input_characters
        self._history_repository = history_repository
        self._usage_guard = usage_guard

    def execute(
        self, compiled_prompt: str, *, prompt_id: str | None = None
    ) -> PromptExecutionOutcome:
        if not compiled_prompt.strip():
            raise InvalidExecutionRequestError("A compiled prompt is required.")
        if len(compiled_prompt) > self._max_input_characters:
            raise InvalidExecutionRequestError("The compiled prompt exceeds the allowed size.")
        if prompt_id is not None:
            if self._history_repository is None:
                raise PromptRecordNotFoundError("Prompt history is unavailable.")
            self._history_repository.get(prompt_id)

        reservation = (
            self._usage_guard.start(UsageAction.PROMPT_EXECUTION)
            if self._usage_guard is not None
            else None
        )

        try:
            result = self._backend.execute(compiled_prompt)
        except ExecutionBackendError:
            if reservation is not None:
                self._usage_guard.release(reservation)
            raise
        except Exception as error:
            if reservation is not None:
                self._usage_guard.release(reservation)
            raise ExecutionBackendError("Prompt execution is unavailable.") from error

        if not isinstance(result.output, str) or not result.output.strip():
            if reservation is not None:
                self._usage_guard.release(reservation)
            raise InvalidExecutionOutputError("Prompt execution returned no usable output.")
        if reservation is not None:
            self._usage_guard.complete(reservation)
        execution_id = None
        if prompt_id is not None:
            execution = self._history_repository.save_execution(
                prompt_id=prompt_id, output=result.output
            )
            execution_id = execution.id
        return PromptExecutionOutcome(output=result.output, execution_id=execution_id)
