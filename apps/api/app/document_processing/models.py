"""Structured, storage-agnostic representations for document text and chunks."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

BlockType = Literal["heading", "paragraph", "list_item", "code"]


@dataclass(frozen=True)
class DocumentMetadata:
    document_id: str
    media_type: str


@dataclass(frozen=True)
class TextBlock:
    block_type: BlockType
    text: str
    order_index: int
    page_number: int | None = None
    heading_level: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    document_id: str
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class NormalizedDocument:
    document_id: str
    blocks: tuple[TextBlock, ...]
    language: str | None


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int = 350
    max_tokens: int = 500
    overlap_tokens: int = 40


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    workspace_id: str
    chunk_index: int
    text: str
    token_count: int
    language: str | None
    page_start: int | None
    page_end: int | None
    section: str | None
    heading: str | None
    source_block_start: int
    source_block_end: int
    created_at: datetime | None = None


@dataclass(frozen=True)
class ChunkStatistics:
    chunk_count: int
    average_token_count: float
    min_token_count: int
    max_token_count: int
