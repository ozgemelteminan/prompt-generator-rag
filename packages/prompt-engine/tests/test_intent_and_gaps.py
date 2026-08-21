from dataclasses import dataclass

import pytest

from prompt_engine.errors import (
    EmptyRawRequestError,
    InvalidStructuredAnalysisOutputError,
    StructuredAnalysisBackendError,
)
from prompt_engine.gaps import GapAnalyzer
from prompt_engine.intent import IntentAnalyzer, StructuredAnalysisRequest
from prompt_engine.presets import TASK_PRESETS, get_task_preset
from prompt_engine.schemas import PromptSpec


@dataclass
class FakeStructuredAnalysisBackend:
    result: object
    request: StructuredAnalysisRequest | None = None

    def analyze(self, request: StructuredAnalysisRequest) -> object:
        self.request = request
        return self.result


class FailingStructuredAnalysisBackend:
    def analyze(self, _: StructuredAnalysisRequest) -> object:
        raise RuntimeError("provider unavailable")


def make_spec(
    *, language: str = "en", missing_information: list[dict[str, str]] | None = None
) -> PromptSpec:
    return PromptSpec(
        task={"type": "general", "objective": "Help with this request."},
        language=language,
        missing_information=missing_information or [],
    )


def test_turkish_request_is_analyzed_through_one_fake_backend_call() -> None:
    backend = FakeStructuredAnalysisBackend(
        {
            "task": {"type": "writing.email", "objective": "Müşteriye proje güncellemesi yaz."},
            "language": "tr",
            "tone": "profesyonel",
            "missingInformation": [],
        }
    )

    result = IntentAnalyzer(backend).analyze(
        "Müşteriye kısa bir proje güncellemesi yaz.", language="tr"
    )

    assert result.task.type == "writing.email"
    assert result.language == "tr"
    assert backend.request is not None
    assert backend.request.input.raw_request == "Müşteriye kısa bir proje güncellemesi yaz."
    assert backend.request.input.language == "tr"
    assert backend.request.response_schema is PromptSpec


def test_english_request_is_analyzed_through_fake_backend() -> None:
    backend = FakeStructuredAnalysisBackend(
        {
            "task": {"type": "research.compare", "objective": "Compare two database options."},
            "language": "en",
            "requirements": ["Focus on operating cost."],
            "missingInformation": [],
        }
    )

    result = IntentAnalyzer(backend).analyze("Compare PostgreSQL and MySQL costs.", language="en")

    assert result.task.type == "research.compare"
    assert result.requirements == ["Focus on operating cost."]
    assert backend.request is not None
    assert "Return only data matching PromptSpec" in backend.request.instructions


def test_preset_is_passed_to_analysis_as_an_optional_hint() -> None:
    backend = FakeStructuredAnalysisBackend(
        {"task": {"type": "research", "objective": "Research the topic."}, "language": "en"}
    )

    IntentAnalyzer(backend).analyze(
        "Research renewable energy.", language="en", preset=get_task_preset("write-email")
    )

    assert backend.request is not None
    assert backend.request.preset is not None
    assert backend.request.preset.id == "write-email"


def test_builtin_presets_are_resolvable_and_do_not_contain_final_prompts() -> None:
    assert len(TASK_PRESETS) >= 10
    assert get_task_preset("debug-code") is not None
    assert get_task_preset("missing") is None


def test_backend_result_is_validated_as_prompt_spec() -> None:
    backend = FakeStructuredAnalysisBackend(make_spec(language="en"))

    result = IntentAnalyzer(backend).analyze("Help me organize this.", language="en")

    assert result == make_spec(language="en")


def test_invalid_backend_output_is_rejected() -> None:
    backend = FakeStructuredAnalysisBackend(
        {"task": {"type": "general", "objective": "Help."}, "language": "de"}
    )

    with pytest.raises(InvalidStructuredAnalysisOutputError):
        IntentAnalyzer(backend).analyze("Help me.", language="en")


def test_backend_language_must_match_the_selected_language() -> None:
    backend = FakeStructuredAnalysisBackend(make_spec(language="tr"))

    with pytest.raises(InvalidStructuredAnalysisOutputError, match="selected language"):
        IntentAnalyzer(backend).analyze("Help me.", language="en")


def test_empty_input_is_rejected_before_calling_backend() -> None:
    backend = FakeStructuredAnalysisBackend(make_spec())

    with pytest.raises(EmptyRawRequestError):
        IntentAnalyzer(backend).analyze("  ", language="en")

    assert backend.request is None


def test_backend_failure_is_wrapped_as_a_domain_error() -> None:
    with pytest.raises(StructuredAnalysisBackendError):
        IntentAnalyzer(FailingStructuredAnalysisBackend()).analyze("Help me.", language="en")


def test_required_gaps_are_selected_before_helpful_gaps() -> None:
    spec = make_spec(
        missing_information=[
            {"field": "tone", "importance": "helpful", "question": "Which tone should I use?"},
            {"field": "audience", "importance": "required", "question": "Who is this for?"},
        ]
    )

    plan = GapAnalyzer().analyze(spec)

    assert [question.field for question in plan.questions] == ["audience", "tone"]
    assert plan.should_clarify is True
    assert plan.can_generate is False


def test_helpful_gaps_are_selected_when_capacity_remains() -> None:
    spec = make_spec(
        missing_information=[
            {"field": "audience", "importance": "helpful", "question": "Who is this for?"}
        ]
    )

    plan = GapAnalyzer().analyze(spec)

    assert [question.field for question in plan.questions] == ["audience"]
    assert plan.can_generate is True


def test_optional_gaps_are_not_surfaced() -> None:
    spec = make_spec(
        missing_information=[
            {"field": "tone", "importance": "optional", "question": "Would you like a tone?"}
        ]
    )

    plan = GapAnalyzer().analyze(spec)

    assert plan.questions == []
    assert plan.should_clarify is False
    assert plan.can_generate is True


def test_clarification_plan_has_a_maximum_of_four_questions() -> None:
    spec = make_spec(
        missing_information=[
            {"field": f"field-{index}", "importance": "required", "question": f"Question {index}?"}
            for index in range(5)
        ]
    )

    assert len(GapAnalyzer().analyze(spec).questions) == 4


def test_duplicate_gaps_and_questions_are_removed_stably() -> None:
    spec = make_spec(
        missing_information=[
            {"field": "audience", "importance": "required", "question": "Who is this for?"},
            {"field": "Audience", "importance": "required", "question": "Which audience?"},
            {"field": "tone", "importance": "helpful", "question": "WHO IS THIS FOR?"},
            {"field": "format", "importance": "helpful", "question": "Which format?"},
        ]
    )

    plan = GapAnalyzer().analyze(spec)

    assert [question.field for question in plan.questions] == ["audience", "format"]


def test_zero_question_plan_for_a_sufficient_prompt_spec() -> None:
    plan = GapAnalyzer().analyze(make_spec())

    assert plan.questions == []
    assert plan.should_clarify is False
    assert plan.can_generate is True


@pytest.mark.parametrize(
    ("language", "question"),
    [
        ("tr", "Bu içerik kimin için hazırlanacak?"),
        ("en", "Who is this content for?"),
    ],
)
def test_clarification_text_is_preserved(language: str, question: str) -> None:
    spec = make_spec(
        language=language,
        missing_information=[{"field": "audience", "importance": "required", "question": question}],
    )

    plan = GapAnalyzer().analyze(spec)

    assert plan.questions[0].question == question
