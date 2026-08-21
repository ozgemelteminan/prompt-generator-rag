"""SQLAlchemy repository for persisted prompt history."""

from datetime import datetime
from uuid import uuid4

from prompt_engine.schemas import PromptSpec
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import PromptExecutionRecord, PromptFeedbackRecord, PromptGenerationRecord


class PromptRecordNotFoundError(Exception):
    """Raised when a local history record cannot be found."""


class PromptHistoryRepository:
    """Persist and retrieve prompt workflow records for the local workspace."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_generation(
        self,
        *,
        original_input: str,
        language: str,
        preset_id: str | None,
        prompt_spec: PromptSpec,
        compiled_prompt: str,
    ) -> str:
        record = PromptGenerationRecord(
            id=str(uuid4()),
            original_input=original_input,
            language=language,
            preset_id=preset_id,
            prompt_spec=prompt_spec.model_dump(mode="json", by_alias=True),
            generation_state="ready",
            compiled_prompt=compiled_prompt,
        )
        self._session.add(record)
        self._session.commit()
        return record.id

    def get(self, prompt_id: str) -> PromptGenerationRecord:
        record = self._session.scalar(
            select(PromptGenerationRecord)
            .where(PromptGenerationRecord.id == prompt_id)
            .options(
                selectinload(PromptGenerationRecord.executions),
                selectinload(PromptGenerationRecord.feedback),
            )
        )
        if record is None:
            raise PromptRecordNotFoundError("Prompt history record was not found.")
        return record

    def list(
        self, *, limit: int, offset: int, favorites_only: bool
    ) -> list[PromptGenerationRecord]:
        query = select(PromptGenerationRecord).order_by(PromptGenerationRecord.created_at.desc())
        if favorites_only:
            query = query.where(PromptGenerationRecord.is_favorite.is_(True))
        return list(
            self._session.scalars(
                query.options(selectinload(PromptGenerationRecord.executions))
                .limit(limit)
                .offset(offset)
            )
        )

    def set_favorite(self, prompt_id: str, is_favorite: bool) -> PromptGenerationRecord:
        record = self.get(prompt_id)
        record.is_favorite = is_favorite
        self._session.commit()
        self._session.refresh(record)
        return record

    def save_execution(self, *, prompt_id: str, output: str) -> PromptExecutionRecord:
        self.get(prompt_id)
        execution = PromptExecutionRecord(id=str(uuid4()), prompt_id=prompt_id, output=output)
        self._session.add(execution)
        self._session.commit()
        return execution

    def save_feedback(
        self,
        *,
        prompt_id: str,
        rating: str,
        reason: str | None,
        comment: str | None,
        execution_id: str | None,
    ) -> PromptFeedbackRecord:
        self.get(prompt_id)
        if execution_id is not None:
            execution = self._session.get(PromptExecutionRecord, execution_id)
            if execution is None or execution.prompt_id != prompt_id:
                raise PromptRecordNotFoundError("Prompt execution record was not found.")
        feedback = PromptFeedbackRecord(
            id=str(uuid4()),
            prompt_id=prompt_id,
            execution_id=execution_id,
            rating=rating,
            reason=reason,
            comment=comment,
        )
        self._session.add(feedback)
        self._session.commit()
        return feedback


def as_iso(value: datetime) -> str:
    """Serialize database timestamps consistently at the API boundary."""
    return value.isoformat()
