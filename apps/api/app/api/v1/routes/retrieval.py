"""Dense retrieval API: metadata-only ranked chunks, never answer generation."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.v1.dependencies import get_dense_retrieval_service
from app.core.errors import ApplicationError
from app.repositories.documents import DocumentNotFoundError
from app.services.retrieval import (
    DenseRetrievalService,
    RetrievalDocumentNotReadyError,
    RetrievalEmbeddingUnavailableError,
    RetrievalError,
    RetrievalInvalidQueryError,
)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class RetrievalSearchRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    query: str
    limit: int | None = None
    document_ids: list[str] = Field(default_factory=list)


class RetrievalResultResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    chunk_id: str
    document_id: str
    filename: str
    chunk_index: int
    text: str
    distance: float
    similarity: float
    page_start: int | None
    page_end: int | None
    section: str | None
    heading: str | None
    source_block_start: int
    source_block_end: int


class RetrievalSearchResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    results: list[RetrievalResultResponse]


@router.post("/search", response_model=RetrievalSearchResponse, summary="Search embedded chunks")
def search(
    request: RetrievalSearchRequest,
    service: Annotated[DenseRetrievalService, Depends(get_dense_retrieval_service)],
) -> RetrievalSearchResponse:
    try:
        results = service.search(
            query=request.query,
            limit=request.limit,
            document_ids=tuple(request.document_ids),
        )
    except RetrievalInvalidQueryError as error:
        raise ApplicationError(
            code="retrieval_invalid_query",
            message="The retrieval query is invalid.",
            status_code=422,
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
    return RetrievalSearchResponse(
        results=[RetrievalResultResponse(**result.__dict__) for result in results]
    )
