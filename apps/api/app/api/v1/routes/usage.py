from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.api.v1.dependencies import get_usage_guard
from app.core.errors import ApplicationError
from app.repositories.usage import UsageAccountingError
from app.services.usage import UsageGuard, as_reset_iso

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ResourceUsageResponse(UsageModel):
    used: int
    limit: int
    remaining: int
    reset_at: str


class UsageStatusResponse(UsageModel):
    generation: ResourceUsageResponse
    execution: ResourceUsageResponse


@router.get("", response_model=UsageStatusResponse, summary="Get current workspace usage")
def get_usage_status(
    guard: Annotated[UsageGuard, Depends(get_usage_guard)],
) -> UsageStatusResponse:
    try:
        status = guard.status()
    except UsageAccountingError as error:
        raise ApplicationError(
            code="usage_accounting_failed",
            message="Usage could not be read safely.",
            status_code=500,
        ) from error
    return UsageStatusResponse(
        generation=ResourceUsageResponse(
            used=status.generation.used,
            limit=status.generation.limit,
            remaining=status.generation.remaining,
            reset_at=as_reset_iso(status.generation.reset_at),
        ),
        execution=ResourceUsageResponse(
            used=status.execution.used,
            limit=status.execution.limit,
            remaining=status.execution.remaining,
            reset_at=as_reset_iso(status.execution.reset_at),
        ),
    )
