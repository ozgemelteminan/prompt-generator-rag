"""Provider-independent boundary for executing a compiled prompt."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExecutionResult:
    """The plain-text result of a compiled prompt execution."""

    output: str


class ExecutionBackend(Protocol):
    """Execute compiled prompt text without depending on a specific provider."""

    def execute(self, compiled_prompt: str) -> ExecutionResult:
        """Return generated text for one compiled prompt."""
