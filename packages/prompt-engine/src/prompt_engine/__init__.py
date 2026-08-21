"""Provider-independent PromptForge prompt-engine domain package."""

from prompt_engine.compiler import GenericPromptCompiler, PromptCompiler
from prompt_engine.execution import ExecutionBackend, ExecutionResult
from prompt_engine.gaps import ClarificationPlan, GapAnalyzer
from prompt_engine.intent import IntentAnalyzer, StructuredAnalysisBackend
from prompt_engine.presets import TASK_PRESETS, TaskPreset, get_task_preset
from prompt_engine.schemas import (
    MissingInformation,
    MissingInformationImportance,
    OutputPreferences,
    PromptSpec,
    SourceReferences,
    Task,
    TaskFamily,
)

__all__ = [
    "MissingInformation",
    "MissingInformationImportance",
    "OutputPreferences",
    "PromptSpec",
    "SourceReferences",
    "Task",
    "TaskFamily",
    "ClarificationPlan",
    "GapAnalyzer",
    "GenericPromptCompiler",
    "ExecutionBackend",
    "ExecutionResult",
    "IntentAnalyzer",
    "PromptCompiler",
    "StructuredAnalysisBackend",
    "TASK_PRESETS",
    "TaskPreset",
    "get_task_preset",
]
