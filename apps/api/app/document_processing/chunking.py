"""Deterministic structure-aware chunking without provider dependencies."""

import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from app.document_processing.models import (
    ChunkingConfig,
    ChunkStatistics,
    DocumentChunk,
    TextBlock,
)

_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
_SENTENCE_PATTERN = re.compile(r".+?(?:[.!?…]+(?=\s|$)|$)", flags=re.DOTALL)
_ABBREVIATIONS = frozenset({"dr.", "mr.", "mrs.", "ms.", "prof.", "vs.", "etc.", "örn.", "vb."})


class Tokenizer:
    """Small local boundary for approximate retrieval-size tokenization."""

    def tokens(self, text: str) -> tuple[str, ...]:
        return tuple(match.group(0) for match in _TOKEN_PATTERN.finditer(text))

    def count(self, text: str) -> int:
        return len(self.tokens(text))

    def split_to_max_tokens(self, text: str, max_tokens: int) -> tuple[str, ...]:
        tokens = self.tokens(text)
        return tuple(
            _join_tokens(tokens[index : index + max_tokens])
            for index in range(0, len(tokens), max_tokens)
        )


@dataclass(frozen=True)
class _Piece:
    text: str
    token_count: int
    section: str | None
    heading: str | None
    page_number: int | None
    source_block_start: int
    source_block_end: int


class StructureAwareChunker:
    def __init__(self, config: ChunkingConfig, tokenizer: Tokenizer | None = None) -> None:
        if config.target_tokens <= 0 or config.max_tokens < config.target_tokens:
            raise ValueError("Chunk token budgets are invalid.")
        if config.overlap_tokens < 0 or config.overlap_tokens >= config.max_tokens:
            raise ValueError("Chunk overlap must be non-negative and smaller than the maximum.")
        self._config = config
        self._tokenizer = tokenizer or Tokenizer()

    def chunk(
        self,
        *,
        document_id: str,
        workspace_id: str,
        language: str | None,
        blocks: tuple[TextBlock, ...],
    ) -> tuple[DocumentChunk, ...]:
        chunks: list[DocumentChunk] = []
        group: list[_Piece] = []
        context: tuple[str | None, str | None] | None = None
        for piece in self._pieces(blocks):
            piece_context = (piece.section, piece.heading)
            if group and piece_context != context:
                chunks.extend(self._chunk_group(document_id, workspace_id, language, group))
                group = []
            group.append(piece)
            context = piece_context
        if group:
            chunks.extend(self._chunk_group(document_id, workspace_id, language, group))
        return tuple(
            DocumentChunk(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"promptforge-chunk:{document_id}:{index}:{chunk.text}:{chunk.source_block_start}:{chunk.source_block_end}",
                    )
                ),
                document_id=document_id,
                workspace_id=workspace_id,
                chunk_index=index,
                text=chunk.text,
                token_count=chunk.token_count,
                language=language,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section=chunk.section,
                heading=chunk.heading,
                source_block_start=chunk.source_block_start,
                source_block_end=chunk.source_block_end,
            )
            for index, chunk in enumerate(chunks)
        )

    def statistics(self, chunks: tuple[DocumentChunk, ...]) -> ChunkStatistics:
        counts = [chunk.token_count for chunk in chunks]
        return ChunkStatistics(
            chunk_count=len(counts),
            average_token_count=sum(counts) / len(counts) if counts else 0.0,
            min_token_count=min(counts) if counts else 0,
            max_token_count=max(counts) if counts else 0,
        )

    def _pieces(self, blocks: tuple[TextBlock, ...]) -> tuple[_Piece, ...]:
        pieces: list[_Piece] = []
        active_heading: str | None = None
        active_section: str | None = None
        for block in blocks:
            if block.block_type == "heading":
                active_heading = block.text
                active_section = block.section or block.text
            section = block.section or active_section
            heading = active_heading or section
            pieces.extend(
                self._split_block(
                    text=block.text,
                    section=section,
                    heading=heading,
                    page_number=block.page_number,
                    source_block_index=block.order_index,
                )
            )
        return tuple(pieces)

    def _split_block(
        self,
        *,
        text: str,
        section: str | None,
        heading: str | None,
        page_number: int | None,
        source_block_index: int,
    ) -> tuple[_Piece, ...]:
        token_count = self._tokenizer.count(text)
        if token_count <= self._config.max_tokens:
            return (
                _Piece(
                    text,
                    token_count,
                    section,
                    heading,
                    page_number,
                    source_block_index,
                    source_block_index,
                ),
            )
        sentences = _sentences(text)
        pieces: list[_Piece] = []
        for sentence in sentences:
            if self._tokenizer.count(sentence) <= self._config.max_tokens:
                pieces.append(
                    _Piece(
                        sentence,
                        self._tokenizer.count(sentence),
                        section,
                        heading,
                        page_number,
                        source_block_index,
                        source_block_index,
                    )
                )
                continue
            pieces.extend(
                _Piece(
                    fragment,
                    self._tokenizer.count(fragment),
                    section,
                    heading,
                    page_number,
                    source_block_index,
                    source_block_index,
                )
                for fragment in self._tokenizer.split_to_max_tokens(
                    sentence, self._config.max_tokens
                )
            )
        return tuple(pieces)

    def _chunk_group(
        self, document_id: str, workspace_id: str, language: str | None, pieces: list[_Piece]
    ) -> list[DocumentChunk]:
        completed: list[DocumentChunk] = []
        current: list[_Piece] = []
        for piece in pieces:
            if current and self._count_pieces((*current, piece)) > self._config.target_tokens:
                completed.append(self._make_chunk(document_id, workspace_id, language, current))
                current = self._overlap_tail(current)
            if current and self._count_pieces((*current, piece)) > self._config.max_tokens:
                current = []
            current.append(piece)
        if current:
            completed.append(self._make_chunk(document_id, workspace_id, language, current))
        return completed

    def _overlap_tail(self, pieces: list[_Piece]) -> list[_Piece]:
        if self._config.overlap_tokens == 0:
            return []
        tail: list[_Piece] = []
        tokens = 0
        for piece in reversed(pieces):
            if tokens + piece.token_count > self._config.overlap_tokens:
                break
            tail.insert(0, piece)
            tokens += piece.token_count
        return tail

    def _count_pieces(self, pieces: tuple[_Piece, ...]) -> int:
        return self._tokenizer.count("\n\n".join(piece.text for piece in pieces))

    def _make_chunk(
        self, document_id: str, workspace_id: str, language: str | None, pieces: list[_Piece]
    ) -> DocumentChunk:
        text = "\n\n".join(piece.text for piece in pieces)
        pages = [piece.page_number for piece in pieces if piece.page_number is not None]
        first = pieces[0]
        return DocumentChunk(
            id="",
            document_id=document_id,
            workspace_id=workspace_id,
            chunk_index=-1,
            text=text,
            token_count=self._tokenizer.count(text),
            language=language,
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            section=first.section,
            heading=first.heading,
            source_block_start=min(piece.source_block_start for piece in pieces),
            source_block_end=max(piece.source_block_end for piece in pieces),
        )


def _sentences(text: str) -> tuple[str, ...]:
    sentences: list[str] = []
    pending = ""
    for match in _SENTENCE_PATTERN.finditer(text.strip()):
        candidate = f"{pending}{match.group(0)}".strip()
        pending = ""
        if candidate.lower().split()[-1] in _ABBREVIATIONS:
            pending = f"{candidate} "
        elif candidate:
            sentences.append(candidate)
    if pending.strip():
        sentences.append(pending.strip())
    return tuple(sentences)


def _join_tokens(tokens: tuple[str, ...]) -> str:
    output = ""
    for token in tokens:
        if not output or token in ".,!?;:%)]}" or output[-1] in "([{":
            output += token
        else:
            output += f" {token}"
    return output
