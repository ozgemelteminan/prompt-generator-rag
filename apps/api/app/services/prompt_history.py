"""Application service for history, favorites, and explicit feedback."""

from app.repositories.prompt_history import PromptHistoryRepository


class PromptHistoryService:
    """Keep persistence operations out of HTTP route handlers."""

    def __init__(self, repository: PromptHistoryRepository) -> None:
        self._repository = repository

    def list(self, *, limit: int, offset: int, favorites_only: bool):
        return self._repository.list(limit=limit, offset=offset, favorites_only=favorites_only)

    def get(self, prompt_id: str):
        return self._repository.get(prompt_id)

    def set_favorite(self, prompt_id: str, is_favorite: bool):
        return self._repository.set_favorite(prompt_id, is_favorite)

    def submit_feedback(
        self,
        *,
        prompt_id: str,
        rating: str,
        reason: str | None,
        comment: str | None,
        execution_id: str | None,
    ):
        return self._repository.save_feedback(
            prompt_id=prompt_id,
            rating=rating,
            reason=reason,
            comment=comment,
            execution_id=execution_id,
        )
