import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from prompt_engine.errors import (
    EmptyRawRequestError,
    ExecutionBackendError,
    IncompletePromptSpecificationError,
    InvalidAnalysisInputError,
    InvalidExecutionOutputError,
    InvalidExecutionRequestError,
    InvalidStructuredAnalysisOutputError,
    StructuredAnalysisBackendError,
    UnknownTaskPresetError,
)
from prompt_engine.gaps import ClarificationPlan
from prompt_engine.schemas import PromptSpec
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.v1.dependencies import (
    get_prompt_execution_service,
    get_prompt_generation_service,
    get_prompt_history_service,
)
from app.core.errors import ApplicationError
from app.db.models import PromptExecutionRecord, PromptFeedbackRecord, PromptGenerationRecord
from app.repositories.documents import DocumentNotFoundError
from app.repositories.prompt_history import PromptRecordNotFoundError, as_iso
from app.repositories.usage import UsageAccountingError, UsageQuotaExceededError
from app.services.prompt_execution import PromptExecutionService
from app.services.prompt_generation import PromptGenerationResult, PromptGenerationService
from app.services.prompt_history import PromptHistoryService
from app.services.retrieval import (
    RetrievalDocumentNotReadyError,
    RetrievalEmbeddingUnavailableError,
    RetrievalError,
)
from app.services.usage import RateLimitExceededError

router = APIRouter(prefix="/prompts", tags=["prompts"])
logger = logging.getLogger(__name__)


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GeneratePromptRequest(ApiModel):
    input: str = Field(min_length=1)
    language: Literal["tr", "en"]
    preset_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)


class GeneratePromptResponse(ApiModel):
    state: Literal["ready", "clarification_required"]
    prompt_spec: PromptSpec
    clarification_plan: ClarificationPlan
    compiled_prompt: str | None
    record_id: str | None


class ExecutePromptRequest(ApiModel):
    compiled_prompt: str
    prompt_id: str | None = None


class ExecutePromptResponse(ApiModel):
    output: str
    execution_id: str | None = None


class ExecutionHistoryResponse(ApiModel):
    id: str
    output: str
    created_at: str


class FeedbackResponse(ApiModel):
    id: str
    rating: Literal["positive", "negative"]
    reason: str | None
    comment: str | None
    execution_id: str | None
    created_at: str


class PromptHistoryItemResponse(ApiModel):
    id: str
    original_input: str
    language: Literal["tr", "en"]
    preset_id: str | None
    is_favorite: bool
    compiled_prompt_preview: str
    latest_execution_preview: str | None
    created_at: str


class PromptHistoryListResponse(ApiModel):
    items: list[PromptHistoryItemResponse]
    limit: int
    offset: int
    next_offset: int | None


class PromptHistoryDetailResponse(ApiModel):
    id: str
    original_input: str
    language: Literal["tr", "en"]
    preset_id: str | None
    prompt_spec: PromptSpec
    compiled_prompt: str
    is_favorite: bool
    created_at: str
    executions: list[ExecutionHistoryResponse]
    feedback: list[FeedbackResponse]


class SetFavoriteRequest(ApiModel):
    is_favorite: bool


class SubmitFeedbackRequest(ApiModel):
    rating: Literal["positive", "negative"]
    reason: str | None = Field(default=None, max_length=80)
    comment: str | None = Field(default=None, max_length=1_000)
    execution_id: str | None = None


@router.post("/generate", response_model=GeneratePromptResponse, summary="Generate a prompt draft")
def generate_prompt(
    request: GeneratePromptRequest,
    service: Annotated[PromptGenerationService, Depends(get_prompt_generation_service)],
) -> GeneratePromptResponse:
    try:
        result = service.generate(
            request.input,
            language=request.language,
            preset_id=request.preset_id,
            document_ids=tuple(request.document_ids),
        )
    except (EmptyRawRequestError, InvalidAnalysisInputError, UnknownTaskPresetError) as error:
        raise ApplicationError(
            code="invalid_request", message="Prompt input is invalid.", status_code=422
        ) from error
    except StructuredAnalysisBackendError as error:
        logger.warning("provider_failure category=analysis_unavailable")
        raise ApplicationError(
            code="analysis_unavailable",
            message="Prompt analysis is temporarily unavailable.",
            status_code=503,
        ) from error
    except InvalidStructuredAnalysisOutputError as error:
        logger.warning("provider_failure category=invalid_analysis_output")
        raise ApplicationError(
            code="invalid_analysis_output",
            message="Prompt analysis returned invalid data.",
            status_code=502,
        ) from error
    except IncompletePromptSpecificationError as error:
        raise ApplicationError(
            code="incomplete_specification",
            message="Required information is missing before prompt generation.",
            status_code=409,
        ) from error
    except DocumentNotFoundError as error:
        raise ApplicationError(
            code="document_not_found", message="The document was not found.", status_code=404
        ) from error
    except RetrievalDocumentNotReadyError as error:
        raise ApplicationError(
            code="retrieval_document_not_ready",
            message="The requested document is not embedded.",
            status_code=409,
        ) from error
    except RetrievalEmbeddingUnavailableError as error:
        raise ApplicationError(
            code="embedding_model_unavailable",
            message="The embedding model is unavailable.",
            status_code=503,
        ) from error
    except RetrievalError as error:
        raise ApplicationError(
            code="retrieval_failed",
            message="Dense retrieval could not be completed.",
            status_code=500,
        ) from error
    except (RateLimitExceededError, UsageQuotaExceededError, UsageAccountingError) as error:
        _raise_usage_error(error)
    return GeneratePromptResponse.model_validate(_serialize_result(result))


@router.post(
    "/execute",
    response_model=ExecutePromptResponse,
    response_model_exclude_none=True,
    summary="Run a compiled prompt",
)
def execute_prompt(
    request: ExecutePromptRequest,
    service: Annotated[PromptExecutionService, Depends(get_prompt_execution_service)],
) -> ExecutePromptResponse:
    try:
        result = service.execute(request.compiled_prompt, prompt_id=request.prompt_id)
    except PromptRecordNotFoundError as error:
        raise ApplicationError(
            code="history_not_found",
            message="Prompt history record was not found.",
            status_code=404,
        ) from error
    except InvalidExecutionRequestError as error:
        raise ApplicationError(
            code="invalid_request", message="Compiled prompt input is invalid.", status_code=422
        ) from error
    except ExecutionBackendError as error:
        logger.warning("provider_failure category=execution_unavailable")
        raise ApplicationError(
            code="execution_unavailable",
            message="Prompt execution is temporarily unavailable.",
            status_code=503,
        ) from error
    except InvalidExecutionOutputError as error:
        logger.warning("provider_failure category=invalid_execution_output")
        raise ApplicationError(
            code="invalid_execution_output",
            message="Prompt execution returned no usable output.",
            status_code=502,
        ) from error
    except (RateLimitExceededError, UsageQuotaExceededError, UsageAccountingError) as error:
        _raise_usage_error(error)
    return ExecutePromptResponse(output=result.output, execution_id=result.execution_id)


@router.get("", response_model=PromptHistoryListResponse, summary="List saved prompt history")
def list_prompt_history(
    service: Annotated[PromptHistoryService, Depends(get_prompt_history_service)],
    limit: int = 20,
    offset: int = 0,
    favorites_only: bool = False,
) -> PromptHistoryListResponse:
    if not 1 <= limit <= 100 or offset < 0:
        raise ApplicationError(
            code="invalid_request", message="History pagination is invalid.", status_code=422
        )
    records = service.list(limit=limit + 1, offset=offset, favorites_only=favorites_only)
    has_next = len(records) > limit
    return PromptHistoryListResponse(
        items=[_serialize_history_item(record) for record in records[:limit]],
        limit=limit,
        offset=offset,
        next_offset=offset + limit if has_next else None,
    )


@router.get("/{prompt_id}", response_model=PromptHistoryDetailResponse, summary="Get saved prompt")
def get_prompt_history_item(
    prompt_id: str,
    service: Annotated[PromptHistoryService, Depends(get_prompt_history_service)],
) -> PromptHistoryDetailResponse:
    try:
        return PromptHistoryDetailResponse.model_validate(
            _serialize_history_detail(service.get(prompt_id))
        )
    except PromptRecordNotFoundError as error:
        raise ApplicationError(
            code="history_not_found",
            message="Prompt history record was not found.",
            status_code=404,
        ) from error


@router.put(
    "/{prompt_id}/favorite", response_model=PromptHistoryItemResponse, summary="Set favorite"
)
def set_prompt_favorite(
    prompt_id: str,
    request: SetFavoriteRequest,
    service: Annotated[PromptHistoryService, Depends(get_prompt_history_service)],
) -> PromptHistoryItemResponse:
    try:
        return PromptHistoryItemResponse.model_validate(
            _serialize_history_item(service.set_favorite(prompt_id, request.is_favorite))
        )
    except PromptRecordNotFoundError as error:
        raise ApplicationError(
            code="history_not_found",
            message="Prompt history record was not found.",
            status_code=404,
        ) from error


@router.post("/{prompt_id}/feedback", response_model=FeedbackResponse, summary="Submit feedback")
def submit_prompt_feedback(
    prompt_id: str,
    request: SubmitFeedbackRequest,
    service: Annotated[PromptHistoryService, Depends(get_prompt_history_service)],
) -> FeedbackResponse:
    try:
        feedback = service.submit_feedback(
            prompt_id=prompt_id,
            rating=request.rating,
            reason=request.reason,
            comment=request.comment,
            execution_id=request.execution_id,
        )
    except PromptRecordNotFoundError as error:
        raise ApplicationError(
            code="history_not_found",
            message="Prompt history record was not found.",
            status_code=404,
        ) from error
    return FeedbackResponse.model_validate(_serialize_feedback(feedback))


def _serialize_result(result: PromptGenerationResult) -> dict[str, object]:
    return {
        "state": result.state,
        "prompt_spec": result.prompt_spec,
        "clarification_plan": result.clarification_plan,
        "compiled_prompt": result.compiled_prompt,
        "record_id": result.record_id,
    }


def _serialize_history_item(record: PromptGenerationRecord) -> dict[str, object]:
    executions = record.executions
    latest = max(executions, key=lambda execution: execution.created_at, default=None)
    return {
        "id": record.id,
        "original_input": record.original_input,
        "language": record.language,
        "preset_id": record.preset_id,
        "is_favorite": record.is_favorite,
        "compiled_prompt_preview": record.compiled_prompt[:240],
        "latest_execution_preview": latest.output[:240] if latest is not None else None,
        "created_at": as_iso(record.created_at),
    }


def _serialize_history_detail(record: PromptGenerationRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "original_input": record.original_input,
        "language": record.language,
        "preset_id": record.preset_id,
        "prompt_spec": record.prompt_spec,
        "compiled_prompt": record.compiled_prompt,
        "is_favorite": record.is_favorite,
        "created_at": as_iso(record.created_at),
        "executions": [_serialize_execution(execution) for execution in record.executions],
        "feedback": [_serialize_feedback(feedback) for feedback in record.feedback],
    }


def _serialize_execution(execution: PromptExecutionRecord) -> dict[str, object]:
    return {
        "id": execution.id,
        "output": execution.output,
        "created_at": as_iso(execution.created_at),
    }


def _serialize_feedback(feedback: PromptFeedbackRecord) -> dict[str, object]:
    return {
        "id": feedback.id,
        "rating": feedback.rating,
        "reason": feedback.reason,
        "comment": feedback.comment,
        "execution_id": feedback.execution_id,
        "created_at": as_iso(feedback.created_at),
    }


def _raise_usage_error(
    error: RateLimitExceededError | UsageQuotaExceededError | UsageAccountingError,
) -> None:
    if isinstance(error, RateLimitExceededError):
        raise ApplicationError(
            code="rate_limit_exceeded",
            message="Requests are being made too quickly.",
            status_code=429,
            details={"retryAfterSeconds": error.retry_after_seconds},
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
    if isinstance(error, UsageQuotaExceededError):
        raise ApplicationError(
            code="usage_quota_exceeded",
            message="The current usage allowance has been reached.",
            status_code=403,
            details={"resetAt": error.reset_at.isoformat()},
        ) from error
    raise ApplicationError(
        code="usage_accounting_failed",
        message="Usage could not be recorded safely.",
        status_code=500,
    ) from error
