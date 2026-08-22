from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from prompt_engine.compiler import GenericPromptCompiler
from prompt_engine.errors import ExecutionBackendError, StructuredAnalysisBackendError
from prompt_engine.gaps import GapAnalyzer
from prompt_engine.intent import IntentAnalyzer, StructuredAnalysisRequest
from sqlalchemy.orm import Session

from app.core.caller import CallerContext
from app.core.config import Settings, get_settings
from app.core.rate_limits import InMemoryRateLimiter
from app.db.session import get_db_session
from app.document_processing.chunking import StructureAwareChunker
from app.document_processing.models import ChunkingConfig
from app.infrastructure.huggingface_embeddings import (
    SELECTED_EMBEDDING_DIMENSION,
    MultilingualE5EmbeddingProvider,
)
from app.infrastructure.llm import ProviderConfigurationError, create_llm_provider
from app.infrastructure.local_document_storage import LocalDocumentStorage
from app.repositories.documents import DocumentRepository
from app.repositories.prompt_history import PromptHistoryRepository
from app.repositories.retrieval import DenseRetrievalRepository
from app.repositories.usage import UsageRepository
from app.services.context import ContextBuilder
from app.services.documents import DocumentService
from app.services.prompt_execution import PromptExecutionService
from app.services.prompt_generation import PromptGenerationService
from app.services.prompt_history import PromptHistoryService
from app.services.rag import GroundedRagService
from app.services.retrieval import DenseRetrievalService
from app.services.usage import ActionPolicy, UsageGuard

SettingsDependency = Annotated[Settings, Depends(get_settings)]


class _UnconfiguredStructuredAnalysisBackend:
    def analyze(self, _: StructuredAnalysisRequest) -> object:
        raise StructuredAnalysisBackendError("Prompt analysis is not configured.")


class _UnconfiguredExecutionBackend:
    def execute(self, _: str) -> object:
        raise ExecutionBackendError("Prompt execution is not configured.")


@lru_cache
def get_rate_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


def get_caller_context(settings: SettingsDependency) -> CallerContext:
    return CallerContext(id=settings.local_workspace_id)


def get_usage_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> UsageRepository:
    return UsageRepository(session)


def get_document_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentRepository:
    return DocumentRepository(session)


def get_dense_retrieval_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> DenseRetrievalRepository:
    return DenseRetrievalRepository(session)


def get_document_storage(settings: SettingsDependency) -> LocalDocumentStorage:
    return LocalDocumentStorage(settings.document_storage_path)


def get_embedding_provider(settings: SettingsDependency) -> MultilingualE5EmbeddingProvider:
    return MultilingualE5EmbeddingProvider(
        model_id=settings.embedding_model_id,
        batch_size=settings.embedding_batch_size,
        device=settings.embedding_device,
        max_input_tokens=settings.embedding_max_input_tokens,
    )


def get_document_service(
    settings: SettingsDependency,
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    storage: Annotated[LocalDocumentStorage, Depends(get_document_storage)],
    embedding_provider: Annotated[MultilingualE5EmbeddingProvider, Depends(get_embedding_provider)],
) -> DocumentService:
    return DocumentService(
        caller=caller,
        repository=repository,
        storage=storage,
        max_upload_bytes=settings.document_max_upload_bytes,
        chunker=StructureAwareChunker(
            ChunkingConfig(
                target_tokens=settings.chunk_target_tokens,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            )
        ),
        embedding_provider=embedding_provider,
        embedding_batch_size=settings.embedding_batch_size,
        embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
    )


def get_dense_retrieval_service(
    settings: SettingsDependency,
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    document_repository: Annotated[DocumentRepository, Depends(get_document_repository)],
    retrieval_repository: Annotated[
        DenseRetrievalRepository, Depends(get_dense_retrieval_repository)
    ],
    embedding_provider: Annotated[MultilingualE5EmbeddingProvider, Depends(get_embedding_provider)],
) -> DenseRetrievalService:
    return DenseRetrievalService(
        caller=caller,
        document_repository=document_repository,
        retrieval_repository=retrieval_repository,
        embedding_provider=embedding_provider,
        default_limit=settings.retrieval_default_limit,
        max_limit=settings.retrieval_max_limit,
        expected_dimension=SELECTED_EMBEDDING_DIMENSION,
        hnsw_ef_search=settings.hnsw_ef_search,
    )


def get_context_builder(settings: SettingsDependency) -> ContextBuilder:
    """Expose the configured deterministic builder for the future grounded workflow."""
    return ContextBuilder(max_tokens=settings.rag_context_max_tokens)


def get_grounded_rag_service(
    settings: SettingsDependency,
    retrieval_service: Annotated[DenseRetrievalService, Depends(get_dense_retrieval_service)],
    context_builder: Annotated[ContextBuilder, Depends(get_context_builder)],
) -> GroundedRagService:
    backend = _execution_backend_from_settings(settings)
    return GroundedRagService(
        retrieval_service=retrieval_service,
        context_builder=context_builder,
        generation_backend=backend,
    )


def get_usage_guard(
    settings: SettingsDependency,
    caller: Annotated[CallerContext, Depends(get_caller_context)],
    rate_limiter: Annotated[InMemoryRateLimiter, Depends(get_rate_limiter)],
    repository: Annotated[UsageRepository, Depends(get_usage_repository)],
) -> UsageGuard:
    return UsageGuard(
        caller=caller,
        rate_limiter=rate_limiter,
        repository=repository,
        generation_policy=ActionPolicy(
            rate_limit=settings.rate_limit_generate_requests,
            rate_window_seconds=settings.rate_limit_window_seconds,
            quota_limit=settings.generation_quota_per_month,
        ),
        execution_policy=ActionPolicy(
            rate_limit=settings.rate_limit_execute_requests,
            rate_window_seconds=settings.rate_limit_window_seconds,
            quota_limit=settings.execution_quota_per_month,
        ),
    )


def get_prompt_history_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> PromptHistoryRepository:
    return PromptHistoryRepository(session)


def get_prompt_history_service(
    repository: Annotated[PromptHistoryRepository, Depends(get_prompt_history_repository)],
) -> PromptHistoryService:
    return PromptHistoryService(repository)


def get_prompt_generation_service(
    settings: SettingsDependency,
    repository: Annotated[PromptHistoryRepository, Depends(get_prompt_history_repository)],
    usage_guard: Annotated[UsageGuard, Depends(get_usage_guard)],
    retrieval_service: Annotated[DenseRetrievalService, Depends(get_dense_retrieval_service)],
    context_builder: Annotated[ContextBuilder, Depends(get_context_builder)],
) -> PromptGenerationService:
    """Build the production workflow from configuration at the API boundary."""
    backend = _analysis_backend_from_settings(settings)
    return PromptGenerationService(
        intent_analyzer=IntentAnalyzer(backend),
        gap_analyzer=GapAnalyzer(),
        compiler=GenericPromptCompiler(),
        recorder=repository,
        usage_guard=usage_guard,
        retrieval_service=retrieval_service,
        context_builder=context_builder,
    )


def get_prompt_execution_service(
    settings: SettingsDependency,
    repository: Annotated[PromptHistoryRepository, Depends(get_prompt_history_repository)],
    usage_guard: Annotated[UsageGuard, Depends(get_usage_guard)],
) -> PromptExecutionService:
    """Build the direct-execution workflow from configuration at the API boundary."""
    backend = _execution_backend_from_settings(settings)
    return PromptExecutionService(
        backend=backend,
        max_input_characters=settings.execution_max_input_characters,
        history_repository=repository,
        usage_guard=usage_guard,
    )


def _analysis_backend_from_settings(settings: Settings) -> object:
    try:
        return create_llm_provider(settings)
    except ProviderConfigurationError:
        return _UnconfiguredStructuredAnalysisBackend()


def _execution_backend_from_settings(settings: Settings) -> object:
    try:
        return create_llm_provider(settings)
    except ProviderConfigurationError:
        return _UnconfiguredExecutionBackend()
