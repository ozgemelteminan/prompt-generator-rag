"""Grounded answer endpoint built from the existing dense retrieval pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.api.v1.dependencies import get_grounded_rag_service
from app.api.v1.routes.retrieval import RetrievalSearchRequest
from app.core.errors import ApplicationError
from app.repositories.documents import DocumentNotFoundError
from app.services.rag import GroundedRagService, RagGenerationError, RagInvalidCitationError
from app.services.retrieval import (
    RetrievalDocumentNotReadyError,
    RetrievalEmbeddingUnavailableError,
    RetrievalError,
    RetrievalInvalidQueryError,
)

router = APIRouter(prefix="/rag", tags=["rag"])


class RagAskRequest(RetrievalSearchRequest):
    document_ids: list[str] = Field(default_factory=list)


class RagSourceResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    citation_id: int
    document_id: str
    chunk_id: str
    filename: str
    page_start: int | None
    page_end: int | None
    section: str | None
    heading: str | None
    excerpt: str
    similarity: float


class RagAskResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    state: str
    answer: str | None
    sources: list[RagSourceResponse]


@router.post(
    "/ask", response_model=RagAskResponse, summary="Answer from selected document evidence"
)
def ask(
    request: RagAskRequest,
    service: Annotated[GroundedRagService, Depends(get_grounded_rag_service)],
) -> RagAskResponse:
    try:
        result = service.ask(
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
            message="The requested document is not ready.",
            status_code=409,
        ) from error
    except RetrievalEmbeddingUnavailableError as error:
        raise ApplicationError(
            code="embedding_model_unavailable",
            message="The embedding model is unavailable.",
            status_code=503,
        ) from error
    except RagInvalidCitationError as error:
        raise ApplicationError(
            code="rag_invalid_citation",
            message="The generated answer contains an invalid citation.",
            status_code=502,
        ) from error
    except RagGenerationError as error:
        raise ApplicationError(
            code="rag_generation_failed",
            message="A grounded answer could not be generated.",
            status_code=502,
        ) from error
    except RetrievalError as error:
        raise ApplicationError(
            code="retrieval_failed",
            message="Dense retrieval could not be completed.",
            status_code=500,
        ) from error
    return RagAskResponse(
        state=result.state,
        answer=result.answer,
        sources=[RagSourceResponse(**source.__dict__) for source in result.sources],
    )
