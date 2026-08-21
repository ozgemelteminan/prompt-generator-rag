from prompt_engine.schemas import PromptSpec
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import Base
from app.repositories.prompt_history import PromptHistoryRepository, PromptRecordNotFoundError


def make_repository() -> PromptHistoryRepository:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return PromptHistoryRepository(Session(engine))


def make_prompt_spec() -> PromptSpec:
    return PromptSpec.model_validate(
        {"task": {"type": "writing.email", "objective": "Write an update."}, "language": "en"}
    )


def test_persisted_generation_round_trips_and_supports_favorites_feedback_and_executions() -> None:
    repository = make_repository()
    prompt_id = repository.save_generation(
        original_input="Write an update.",
        language="en",
        preset_id="write-email",
        prompt_spec=make_prompt_spec(),
        compiled_prompt="OBJECTIVE\nWrite an update.",
    )

    assert repository.get(prompt_id).prompt_spec == make_prompt_spec().model_dump(
        mode="json", by_alias=True
    )
    assert repository.list(limit=1, offset=0, favorites_only=False)[0].id == prompt_id
    assert repository.list(limit=1, offset=1, favorites_only=False) == []
    assert repository.set_favorite(prompt_id, True).is_favorite is True
    assert len(repository.list(limit=1, offset=0, favorites_only=True)) == 1

    first = repository.save_execution(prompt_id=prompt_id, output="First answer")
    second = repository.save_execution(prompt_id=prompt_id, output="Second answer")
    feedback = repository.save_feedback(
        prompt_id=prompt_id,
        execution_id=second.id,
        rating="negative",
        reason="Too long",
        comment="Please be shorter.",
    )

    record = repository.get(prompt_id)
    assert [execution.output for execution in record.executions] == [
        "First answer",
        "Second answer",
    ]
    assert feedback.execution_id == second.id
    assert record.prompt_spec["task"] == {"type": "writing.email", "objective": "Write an update."}
    assert first.id != second.id


def test_invalid_history_ids_are_safe() -> None:
    repository = make_repository()

    try:
        repository.get("missing")
    except PromptRecordNotFoundError:
        pass
    else:
        raise AssertionError("A missing record must not be returned.")
