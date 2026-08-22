"""Canonical, model-independent representation of user prompt intent."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class PromptEngineModel(BaseModel):
    """Shared JSON conventions for Prompt Engine domain models."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TaskFamily(StrEnum):
    WRITING = "writing"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    CODING = "coding"
    LEARNING = "learning"
    SUMMARIZATION = "summarization"
    BRAINSTORMING = "brainstorming"
    PLANNING = "planning"
    TRANSLATION = "translation"
    DATA = "data"
    IMAGE_GENERATION = "image_generation"
    GENERAL = "general"


class Task(PromptEngineModel):
    """The task family, optional extensible subtype, and intended outcome."""

    type: str
    objective: str = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        parts = value.split(".")
        if not value or any(not part for part in parts):
            raise ValueError("task type must be a family or dot-separated subtype")
        if parts[0] not in {family.value for family in TaskFamily}:
            raise ValueError("task type must begin with a supported task family")
        return value

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("objective must not be empty")
        return stripped_value


class OutputPreferences(PromptEngineModel):
    """Requested response presentation without constraining implementation providers."""

    format: str | None = None
    length: Literal["short", "medium", "long"] | None = None
    structure: list[str] = Field(default_factory=list)


class SourceContext(PromptEngineModel):
    """A bounded retrieved excerpt available to deterministic prompt compilation."""

    citation_id: int = Field(gt=0)
    document_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    text: str = Field(min_length=1)


class SourceReferences(PromptEngineModel):
    """Optional selected identifiers and bounded retrieved source excerpts."""

    document_ids: list[str] = Field(default_factory=list)
    context: list[SourceContext] = Field(default_factory=list)


class MissingInformationImportance(StrEnum):
    REQUIRED = "required"
    HELPFUL = "helpful"
    OPTIONAL = "optional"


class MissingInformation(PromptEngineModel):
    field: str = Field(min_length=1)
    importance: MissingInformationImportance
    question: str = Field(min_length=1)

    @field_validator("field", "question")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("missing-information text must not be empty")
        return stripped_value


class PromptSpec(PromptEngineModel):
    """Canonical structured representation of a user's prompt intent."""

    version: Literal["1.0"] = "1.0"
    task: Task
    language: Literal["tr", "en"]
    context: str | None = None
    audience: str | None = None
    tone: str | None = None
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    output: OutputPreferences = Field(default_factory=OutputPreferences)
    sources: SourceReferences | None = None
    missing_information: list[MissingInformation] = Field(default_factory=list)
