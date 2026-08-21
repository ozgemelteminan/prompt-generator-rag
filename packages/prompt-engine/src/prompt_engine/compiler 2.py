"""Provider-agnostic contract for the future Prompt Compiler."""

from typing import Protocol

from prompt_engine.schemas import PromptSpec


class PromptCompiler(Protocol):
    def compile(self, prompt_spec: PromptSpec) -> str:
        """Compile a PromptSpec into an executable prompt."""
