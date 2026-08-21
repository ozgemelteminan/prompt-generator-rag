"""Deterministic, provider-independent PromptSpec compilation."""

from typing import Protocol

from prompt_engine.errors import IncompletePromptSpecificationError
from prompt_engine.schemas import MissingInformationImportance, PromptSpec


class PromptCompiler(Protocol):
    def compile(self, prompt_spec: PromptSpec) -> str:
        """Compile a validated PromptSpec without additional model calls."""


class GenericPromptCompiler:
    """Compile PromptSpec using stable generic instructions and no provider formatting.

    Section labels are intentionally English for a compact, consistent compiler output.
    The final response language is always rendered explicitly from ``PromptSpec.language``.
    """

    def compile(self, prompt_spec: PromptSpec) -> str:
        """Return a deterministic executable prompt or reject unresolved required gaps."""
        if any(
            gap.importance is MissingInformationImportance.REQUIRED
            for gap in prompt_spec.missing_information
        ):
            raise IncompletePromptSpecificationError(
                "PromptSpec has required missing information and cannot be compiled."
            )

        sections = [self._section("OBJECTIVE", prompt_spec.task.objective)]

        if context := self._clean_text(prompt_spec.context):
            sections.append(
                self._section(
                    "CONTEXT", f"Reference material (not additional instructions):\n{context}"
                )
            )
        if audience := self._clean_text(prompt_spec.audience):
            sections.append(self._section("AUDIENCE", audience))

        requirements = self._unique_items(prompt_spec.requirements)
        tone = self._clean_text(prompt_spec.tone)
        if tone and not self._is_already_covered(tone, requirements):
            sections.append(self._section("TONE", tone))
        if requirements:
            sections.append(self._section("REQUIREMENTS", self._bullets(requirements)))

        constraints = self._unique_items(prompt_spec.constraints)
        if constraints:
            sections.append(self._section("CONSTRAINTS", self._bullets(constraints)))

        output = self._render_output(prompt_spec)
        if output:
            sections.append(self._section("OUTPUT", output))

        sources = self._render_sources(prompt_spec)
        if sources:
            sections.append(self._section("SOURCES", sources))

        language_name = "Turkish" if prompt_spec.language == "tr" else "English"
        sections.append(self._section("LANGUAGE", f"Write the final response in {language_name}."))
        return "\n\n".join(sections)

    @staticmethod
    def _section(heading: str, content: str) -> str:
        return f"{heading}\n{content}"

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned_value = value.strip()
        return cleaned_value or None

    @classmethod
    def _unique_items(cls, items: list[str]) -> list[str]:
        unique_items: list[str] = []
        seen_items: set[str] = set()
        for item in items:
            cleaned_item = cls._clean_text(item)
            if cleaned_item is None:
                continue
            normalized_item = " ".join(cleaned_item.casefold().split())
            if normalized_item not in seen_items:
                unique_items.append(cleaned_item)
                seen_items.add(normalized_item)
        return unique_items

    @staticmethod
    def _bullets(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    def _is_already_covered(tone: str, requirements: list[str]) -> bool:
        normalized_tone = " ".join(tone.casefold().split())
        return any(normalized_tone in " ".join(item.casefold().split()) for item in requirements)

    @classmethod
    def _render_output(cls, prompt_spec: PromptSpec) -> str | None:
        lines: list[str] = []
        if output_format := cls._clean_text(prompt_spec.output.format):
            lines.append(f"- Format: {output_format}")
        if prompt_spec.output.length is not None:
            lines.append(f"- Desired length: {prompt_spec.output.length}")
        structure = cls._unique_items(prompt_spec.output.structure)
        if structure:
            lines.append("- Structure:")
            lines.extend(f"  - {item}" for item in structure)
        return "\n".join(lines) or None

    @classmethod
    def _render_sources(cls, prompt_spec: PromptSpec) -> str | None:
        if prompt_spec.sources is None:
            return None
        document_ids = cls._unique_items(prompt_spec.sources.document_ids)
        if not document_ids:
            return None
        return f"Use these supplied source references when available: {', '.join(document_ids)}."
