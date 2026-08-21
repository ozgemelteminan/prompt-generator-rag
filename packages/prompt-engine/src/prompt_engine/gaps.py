"""Deterministic selection of user-facing clarification questions."""

from prompt_engine.schemas import (
    MissingInformation,
    MissingInformationImportance,
    PromptEngineModel,
    PromptSpec,
)


class ClarificationPlan(PromptEngineModel):
    """A deterministic, non-duplicating decision about whether to ask questions."""

    questions: list[MissingInformation]
    should_clarify: bool
    can_generate: bool


class GapAnalyzer:
    """Surface at most four high-value gaps without making another model call.

    Required gaps are selected first, followed by helpful gaps in their original order.
    Optional gaps are intentionally not surfaced. A duplicate field or question is omitted,
    keeping the earliest item to make selection stable.
    """

    max_questions = 4

    def analyze(self, prompt_spec: PromptSpec) -> ClarificationPlan:
        questions: list[MissingInformation] = []
        seen_fields: set[str] = set()
        seen_questions: set[str] = set()

        for importance in (
            MissingInformationImportance.REQUIRED,
            MissingInformationImportance.HELPFUL,
        ):
            for gap in prompt_spec.missing_information:
                if gap.importance is not importance or len(questions) == self.max_questions:
                    continue

                normalized_field = self._normalize(gap.field)
                normalized_question = self._normalize(gap.question)
                if normalized_field in seen_fields or normalized_question in seen_questions:
                    continue

                questions.append(gap)
                seen_fields.add(normalized_field)
                seen_questions.add(normalized_question)

        has_required_gap = any(
            gap.importance is MissingInformationImportance.REQUIRED
            for gap in prompt_spec.missing_information
        )
        return ClarificationPlan(
            questions=questions,
            should_clarify=bool(questions),
            can_generate=not has_required_gap,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
