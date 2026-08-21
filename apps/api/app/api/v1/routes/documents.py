from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.api.v1.dependencies import get_document_service
from app.core.errors import ApplicationError
from app.db.models import DocumentRecord
from app.infrastructure.local_document_storage import DocumentStorageError
from app.repositories.documents import DocumentNotFoundError
from app.services.documents import (
    DocumentChunkingError,
    DocumentEmptyError,
    DocumentInvalidFilenameError,
    DocumentNoExtractableTextError,
    DocumentNotParsedError,
    DocumentParseError,
    DocumentService,
    DocumentTooLargeError,
    DocumentUnsupportedTypeError,
)

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    filename: str
    media_type: str
    size: int
    language: str | None
    status: str
    checksum: str
    created_at: str
    updated_at: str
    deduplicated: bool = False


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[DocumentResponse]


class DocumentChunkingResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    document_id: str
    status: str
    chunk_count: int
    average_token_count: float
    min_token_count: int
    max_token_count: int


@router.post("", response_model=DocumentResponse, summary="Upload a document")
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF, DOCX, TXT, or Markdown document")],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    try:
        result = await service.upload(file)
    except DocumentEmptyError as error:
        raise ApplicationError(
            code="document_empty", message="The document file is empty.", status_code=422
        ) from error
    except DocumentTooLargeError as error:
        raise ApplicationError(
            code="document_too_large",
            message="The document exceeds the upload limit.",
            status_code=413,
        ) from error
    except DocumentUnsupportedTypeError as error:
        raise ApplicationError(
            code="document_unsupported_type",
            message="The document type is not supported.",
            status_code=415,
        ) from error
    except DocumentInvalidFilenameError as error:
        raise ApplicationError(
            code="invalid_request", message="The document filename is invalid.", status_code=422
        ) from error
    except DocumentStorageError as error:
        raise ApplicationError(
            code="document_storage_failed",
            message="The document could not be stored safely.",
            status_code=500,
        ) from error
    return _serialize_document(result.record, deduplicated=result.deduplicated)


@router.get("", response_model=DocumentListResponse, summary="List documents")
def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentListResponse:
    return DocumentListResponse(items=[_serialize_document(record) for record in service.list()])


@router.get("/{document_id}", response_model=DocumentResponse, summary="Get document metadata")
def get_document(
    document_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    try:
        return _serialize_document(service.get(document_id))
    except DocumentNotFoundError as error:
        raise ApplicationError(
            code="document_not_found", message="The document was not found.", status_code=404
        ) from error


@router.post("/{document_id}/process", response_model=DocumentResponse, summary="Parse a document")
def process_document(
    document_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    try:
        return _serialize_document(service.process(document_id))
    except DocumentNotFoundError as error:
        raise ApplicationError(
            code="document_not_found", message="The document was not found.", status_code=404
        ) from error
    except DocumentNoExtractableTextError as error:
        raise ApplicationError(
            code="document_no_extractable_text",
            message="No extractable text was found in this document.",
            status_code=422,
        ) from error
    except DocumentParseError as error:
        raise ApplicationError(
            code="document_parse_failed",
            message="The document could not be parsed.",
            status_code=422,
        ) from error
    except DocumentStorageError as error:
        raise ApplicationError(
            code="document_storage_failed",
            message="The document could not be read safely.",
            status_code=500,
        ) from error


@router.post(
    "/{document_id}/chunk",
    response_model=DocumentChunkingResponse,
    summary="Chunk a parsed document",
)
def chunk_document(
    document_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentChunkingResponse:
    try:
        result = service.chunk(document_id)
    except DocumentNotFoundError as error:
        raise ApplicationError(
            code="document_not_found", message="The document was not found.", status_code=404
        ) from error
    except DocumentNotParsedError as error:
        raise ApplicationError(
            code="document_not_parsed",
            message="The document must be parsed before it can be chunked.",
            status_code=409,
        ) from error
    except DocumentChunkingError as error:
        raise ApplicationError(
            code="document_chunking_failed",
            message="The document could not be chunked.",
            status_code=422,
        ) from error
    return DocumentChunkingResponse(
        document_id=result.record.id,
        status=result.record.ingestion_status,
        chunk_count=result.statistics.chunk_count,
        average_token_count=result.statistics.average_token_count,
        min_token_count=result.statistics.min_token_count,
        max_token_count=result.statistics.max_token_count,
    )


@router.delete("/{document_id}", status_code=204, summary="Delete document")
def delete_document(
    document_id: str,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> None:
    try:
        service.delete(document_id)
    except DocumentNotFoundError as error:
        raise ApplicationError(
            code="document_not_found", message="The document was not found.", status_code=404
        ) from error
    except DocumentStorageError as error:
        raise ApplicationError(
            code="document_storage_failed",
            message="The document could not be deleted safely.",
            status_code=500,
        ) from error


def _serialize_document(record: DocumentRecord, *, deduplicated: bool = False) -> DocumentResponse:
    return DocumentResponse(
        id=record.id,
        filename=record.original_filename,
        media_type=record.media_type,
        size=record.file_size,
        language=record.language,
        status=record.ingestion_status,
        checksum=record.checksum,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        deduplicated=deduplicated,
    )
