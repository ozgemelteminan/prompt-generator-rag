"""Application workflow for one-call prompt generation."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from prompt_engine.compiler import PromptCompiler
from prompt_engine.errors import EmptyRawRequestError, UnknownTaskPresetError
from prompt_engine.gaps import ClarificationPlan, GapAnalyzer
from prompt_engine.intent import IntentAnalyzer
from prompt_engine.presets import get_task_preset
from prompt_engine.schemas import PromptSpec, SourceContext, SourceReferences

from app.services.context import ContextBuilder, ContextPackage
from app.services.retrieval import DenseRetrievalService
from app.services.usage import UsageAction, UsageGuard


class GenerationState(StrEnum):
    READY = "ready"
    CLARIFICATION_REQUIRED = "clarification_required"


@dataclass(frozen=True)
class PromptGenerationResult:
    prompt_spec: PromptSpec
    clarification_plan: ClarificationPlan
    state: GenerationState
    compiled_prompt: str | None
    record_id: str | None = None


class PromptGenerationRecorder(Protocol):
    """Application persistence boundary for ready prompt generations."""

    def save_generation(
        self,
        *,
        original_input: str,
        language: str,
        preset_id: str | None,
        prompt_spec: PromptSpec,
        compiled_prompt: str,
    ) -> str: ...


class PromptGenerationService:
    """Coordinate analysis, deterministic gap selection, and allowed compilation."""

    def __init__(
        self,
        *,
        intent_analyzer: IntentAnalyzer,
        gap_analyzer: GapAnalyzer,
        compiler: PromptCompiler,
        recorder: PromptGenerationRecorder | None = None,
        usage_guard: UsageGuard | None = None,
        retrieval_service: DenseRetrievalService | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._intent_analyzer = intent_analyzer
        self._gap_analyzer = gap_analyzer
        self._compiler = compiler
        self._recorder = recorder
        self._usage_guard = usage_guard
        self._retrieval_service = retrieval_service
        self._context_builder = context_builder

    def generate(
        self,
        raw_request: str,
        *,
        language: str,
        preset_id: str | None = None,
        document_ids: tuple[str, ...] = (),
    ) -> PromptGenerationResult:
        if not raw_request.strip():
            raise EmptyRawRequestError("A user request is required.")
        preset = get_task_preset(preset_id) if preset_id is not None else None
        if preset_id is not None and preset is None:
            raise UnknownTaskPresetError("The requested task preset is not available.")

        reservation = (
            self._usage_guard.start(UsageAction.PROMPT_GENERATION)
            if self._usage_guard is not None
            else None
        )
        try:
            document_context = self._retrieve_document_context(raw_request, document_ids)
            prompt_spec = self._intent_analyzer.analyze(
                raw_request,
                language=language,
                preset=preset,
                document_context=(
                    (document_context.context_text or None)
                    if document_context is not None
                    else None
                ),
                document_context_requested=bool(document_ids),
            )
        except Exception:
            if reservation is not None:
                self._usage_guard.release(reservation)
            raise
        if reservation is not None:
            self._usage_guard.complete(reservation)
        if document_context is not None:
            prompt_spec = prompt_spec.model_copy(
                update={
                    "sources": (
                        _source_references(document_context) if document_context.sources else None
                    )
                }
            )
        clarification_plan = self._gap_analyzer.analyze(prompt_spec)

        if not clarification_plan.can_generate:
            return PromptGenerationResult(
                prompt_spec=prompt_spec,
                clarification_plan=clarification_plan,
                state=GenerationState.CLARIFICATION_REQUIRED,
                compiled_prompt=None,
            )

        compiled_prompt = self._compiler.compile(prompt_spec)
        record_id = None
        if self._recorder is not None:
            record_id = self._recorder.save_generation(
                original_input=raw_request,
                language=language,
                preset_id=preset_id,
                prompt_spec=prompt_spec,
                compiled_prompt=compiled_prompt,
            )
        return PromptGenerationResult(
            prompt_spec=prompt_spec,
            clarification_plan=clarification_plan,
            state=GenerationState.READY,
            compiled_prompt=compiled_prompt,
            record_id=record_id,
        )

    def _retrieve_document_context(
        self, raw_request: str, document_ids: tuple[str, ...]
    ) -> ContextPackage | None:
        if not document_ids:
            return None
        if self._retrieval_service is None or self._context_builder is None:
            raise RuntimeError("Document-aware prompt generation is not configured.")
        retrieved = self._retrieval_service.search(
            query=raw_request,
            document_ids=tuple(dict.fromkeys(document_ids)),
        )
        return self._context_builder.build(retrieved)


def _source_references(context: ContextPackage) -> SourceReferences:
    return SourceReferences(
        document_ids=list(dict.fromkeys(source.document_id for source in context.sources)),
        context=[
            SourceContext(
                citation_id=source.citation_id,
                document_id=source.document_id,
                filename=source.filename,
                text=source.text,
            )
            for source in context.sources
        ],
    )
