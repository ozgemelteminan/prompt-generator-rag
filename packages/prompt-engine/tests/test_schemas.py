import pytest
from pydantic import ValidationError

from prompt_engine.schemas import (
    MissingInformation,
    MissingInformationImportance,
    PromptSpec,
    Task,
)


def test_valid_turkish_prompt_spec() -> None:
    spec = PromptSpec(
        task=Task(type="writing.email", objective="Müşteriye gecikmeyi açıklayan e-posta yaz."),
        language="tr",
        requirements=["Kısa ve nazik olsun."],
        missing_information=[
            MissingInformation(
                field="recipient",
                importance=MissingInformationImportance.HELPFUL,
                question="E-posta kime gönderilecek?",
            )
        ],
    )

    assert spec.language == "tr"
    assert spec.task.type == "writing.email"
    assert spec.missing_information[0].importance == MissingInformationImportance.HELPFUL


def test_valid_english_prompt_spec() -> None:
    spec = PromptSpec(
        task={"type": "research.compare", "objective": "Compare two database options."},
        language="en",
        output={"format": "table", "length": "short", "structure": ["recommendation"]},
        sources={"documentIds": ["document-123"]},
    )

    assert spec.output.format == "table"
    assert spec.sources is not None
    assert spec.sources.document_ids == ["document-123"]


def test_json_round_trip_uses_camel_case_schema() -> None:
    spec = PromptSpec(
        task={"type": "coding.debug", "objective": "Find the failing test."},
        language="en",
        missing_information=[
            {"field": "error_message", "importance": "required", "question": "What error appears?"}
        ],
    )

    serialized = spec.model_dump_json(by_alias=True)
    restored = PromptSpec.model_validate_json(serialized)

    assert restored == spec
    assert '"missingInformation"' in serialized


def test_invalid_language_is_rejected() -> None:
    with pytest.raises(ValidationError, match="language"):
        PromptSpec(task={"type": "general", "objective": "Help me."}, language="de")


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="version"):
        PromptSpec(version="2.0", task={"type": "general", "objective": "Help me."}, language="en")


def test_invalid_importance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="importance"):
        MissingInformation(field="audience", importance="critical", question="Who is this for?")


def test_missing_objective_is_rejected() -> None:
    with pytest.raises(ValidationError, match="objective"):
        PromptSpec(task={"type": "general", "objective": "   "}, language="en")


def test_defaults_are_safe_and_independent() -> None:
    first = PromptSpec(task={"type": "general", "objective": "Help."}, language="en")
    second = PromptSpec(task={"type": "general", "objective": "Assist."}, language="en")

    first.requirements.append("Use plain language.")
    first.output.structure.append("steps")

    assert second.requirements == []
    assert second.constraints == []
    assert second.output.structure == []
    assert second.missing_information == []


def test_task_subtypes_are_extensible_within_supported_families() -> None:
    assert Task(type="coding.debug", objective="Fix it.").type == "coding.debug"
    assert Task(type="research.compare.regional", objective="Compare options.").type == (
        "research.compare.regional"
    )

    with pytest.raises(ValidationError, match="supported task family"):
        Task(type="unsupported.review", objective="Review this.")
