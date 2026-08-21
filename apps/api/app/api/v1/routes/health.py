from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse, summary="Check API availability")
def get_health() -> HealthResponse:
    """Return API process availability without depending on future domain services."""
    return HealthResponse(status="ok")
