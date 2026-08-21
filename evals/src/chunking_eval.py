"""Chunking-only experiment harness; production chunking is imported, never copied."""

import csv
import hashlib
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Protocol

from app.document_processing.chunking import StructureAwareChunker, Tokenizer
from app.document_processing.models import ChunkingConfig, TextBlock

from evals.src.dataset import EvaluationDataset, EvaluationDocument, EvaluationQuery
from evals.src.metrics import aggregate_rankings


@dataclass(frozen=True)
class EvaluationChunk:
    text: str
    source_block_ids: frozenset[str]
    document_id: str
    chunk_index: int
    language: str
    token_count: int


class EvaluationEmbedder(Protocol):
    model_name: str
    is_official: bool

    def encode(self, texts: list[str]) -> list[list[float]]: ...

    def truncation_rate(self, texts: list[str]) -> float: ...


class DebugHashEmbedder:
    """Offline smoke-test embedder only; never use its results as official metrics."""

    model_name = "debug-hash-embedder-not-for-results"
    is_official = False

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text) for text in texts]

    def truncation_rate(self, texts: list[str]) -> float:
        return 0.0


class SentenceTransformerEmbedder:
    """Lazy real-model adapter for Colab; keeps model details outside experiment logic."""

    is_official = True

    def __init__(
        self,
        model_name: str = "Alibaba-NLP/gte-multilingual-base",
        trust_remote_code: bool = False,
    ) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.trust_remote_code = trust_remote_code
        self._model = SentenceTransformer(
            model_name, trust_remote_code=trust_remote_code
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def truncation_rate(self, texts: list[str]) -> float:
        tokenizer = self._model.tokenizer
        limit = self._model.max_seq_length
        lengths = [
            len(tokenizer(text, truncation=False)["input_ids"]) for text in texts
        ]
        return (
            sum(length > limit for length in lengths) / len(lengths) if lengths else 0.0
        )


@dataclass(frozen=True)
class StrategyResult:
    name: str
    chunk_statistics: dict[str, float | int]
    overall: dict[str, float]
    by_category: dict[str, dict[str, float]]
    by_language: dict[str, dict[str, float]]


def fixed_size_chunks(
    document: EvaluationDocument, *, max_tokens: int = 500, overlap_tokens: int = 40
) -> tuple[EvaluationChunk, ...]:
    tokenizer = Tokenizer()
    token_items = [
        (token, block.id)
        for block in document.blocks
        for token in tokenizer.tokens(block.text)
    ]
    stride = max_tokens - overlap_tokens
    if max_tokens <= 0 or stride <= 0:
        raise ValueError("Fixed chunk token settings are invalid.")
    chunks: list[EvaluationChunk] = []
    for start in range(0, len(token_items), stride):
        window = token_items[start : start + max_tokens]
        if not window:
            break
        chunks.append(
            EvaluationChunk(
                text=_join_tokens(tuple(token for token, _ in window)),
                source_block_ids=frozenset(block_id for _, block_id in window),
                document_id=document.id,
                chunk_index=len(chunks),
                language=document.language,
                token_count=len(window),
            )
        )
        if start + max_tokens >= len(token_items):
            break
    return tuple(chunks)


def recursive_chunks(
    document: EvaluationDocument, *, target_tokens: int = 350, max_tokens: int = 500
) -> tuple[EvaluationChunk, ...]:
    """Evaluation-only recursive baseline: block, sentence, then token boundaries."""
    tokenizer = Tokenizer()
    if target_tokens <= 0 or max_tokens < target_tokens:
        raise ValueError("Recursive chunk token settings are invalid.")
    units: list[tuple[str, str]] = []
    for block in document.blocks:
        if tokenizer.count(block.text) <= max_tokens:
            units.append((block.text, block.id))
            continue
        for sentence in _sentences(block.text):
            if tokenizer.count(sentence) <= max_tokens:
                units.append((sentence, block.id))
            else:
                tokens = tokenizer.tokens(sentence)
                units.extend(
                    (_join_tokens(tokens[index : index + max_tokens]), block.id)
                    for index in range(0, len(tokens), max_tokens)
                )
    return _pack_units(document, units, tokenizer, target_tokens)


def production_structure_aware_chunks(
    document: EvaluationDocument, *, config: ChunkingConfig
) -> tuple[EvaluationChunk, ...]:
    """Adapter over the production source of truth, without reimplementing it."""
    production_blocks = tuple(
        TextBlock(
            block_type=block.block_type,  # type: ignore[arg-type]
            text=block.text,
            order_index=block.order_index,
            page_number=block.page_number,
            section=block.section,
        )
        for block in document.blocks
    )
    chunks = StructureAwareChunker(config).chunk(
        document_id=document.id,
        workspace_id="evaluation-workspace",
        language=document.language,
        blocks=production_blocks,
    )
    block_ids = [block.id for block in document.blocks]
    return tuple(
        EvaluationChunk(
            text=chunk.text,
            source_block_ids=frozenset(
                block_ids[chunk.source_block_start : chunk.source_block_end + 1]
            ),
            document_id=document.id,
            chunk_index=chunk.chunk_index,
            language=document.language,
            token_count=chunk.token_count,
        )
        for chunk in chunks
    )


def run_chunking_experiment(
    dataset: EvaluationDataset,
    *,
    embedder: EvaluationEmbedder,
    strategy_name: str,
    chunks: tuple[EvaluationChunk, ...],
) -> StrategyResult:
    query_embeddings = embedder.encode([query.text for query in dataset.queries])
    return _run_with_query_embeddings(
        dataset, embedder, strategy_name, chunks, query_embeddings
    )


def run_comparison(
    dataset: EvaluationDataset,
    *,
    embedder: EvaluationEmbedder,
    strategies: dict[str, tuple[EvaluationChunk, ...]],
) -> list[StrategyResult]:
    """Encode queries once so chunking strategy is the only experimental variable."""
    query_embeddings = embedder.encode([query.text for query in dataset.queries])
    return [
        _run_with_query_embeddings(dataset, embedder, name, chunks, query_embeddings)
        for name, chunks in strategies.items()
    ]


def _run_with_query_embeddings(
    dataset: EvaluationDataset,
    embedder: EvaluationEmbedder,
    strategy_name: str,
    chunks: tuple[EvaluationChunk, ...],
    query_embeddings: list[list[float]],
) -> StrategyResult:
    chunk_embeddings = embedder.encode([chunk.text for chunk in chunks])
    rankings = [
        _ranking_block_coverage(query, chunks, chunk_embeddings, query_embedding)
        for query, query_embedding in zip(
            dataset.queries, query_embeddings, strict=True
        )
    ]
    return StrategyResult(
        name=strategy_name,
        chunk_statistics=chunk_statistics(chunks, embedder),
        overall=aggregate_rankings(
            rankings, [query.relevant_block_ids for query in dataset.queries]
        ),
        by_category=_group_metrics(
            dataset.queries, rankings, lambda query: query.category
        ),
        by_language=_group_metrics(
            dataset.queries, rankings, lambda query: query.language
        ),
    )


def chunk_statistics(
    chunks: tuple[EvaluationChunk, ...], embedder: EvaluationEmbedder
) -> dict[str, float | int]:
    counts = [chunk.token_count for chunk in chunks]
    return {
        "chunk_count": len(chunks),
        "mean_tokens": statistics.mean(counts) if counts else 0.0,
        "median_tokens": statistics.median(counts) if counts else 0.0,
        "min_tokens": min(counts) if counts else 0,
        "max_tokens": max(counts) if counts else 0,
        "std_tokens": statistics.pstdev(counts) if len(counts) > 1 else 0.0,
        "overlap_ratio": _overlap_ratio(chunks),
        "embedding_truncation_rate": embedder.truncation_rate(
            [chunk.text for chunk in chunks]
        ),
    }


def save_results(
    results: list[StrategyResult],
    *,
    dataset_version: str,
    embedder: EvaluationEmbedder,
    output_dir: Path,
    chunker_configurations: dict[str, dict[str, int]],
) -> None:
    if not embedder.is_official:
        raise ValueError(
            "Debug hash embeddings must not write official benchmark results."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m4.1",
        "datasetVersion": dataset_version,
        "embeddingModel": embedder.model_name,
        "chunkerConfigurations": chunker_configurations,
        "timestamp": datetime.now(UTC).isoformat(),
        "results": [asdict(result) for result in results],
    }
    (output_dir / "chunking_results_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "chunking_results_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "chunker",
                "avg_tokens",
                "recall_at_5",
                "recall_at_10",
                "mrr",
                "ndcg_at_10",
                "hit_rate_at_5",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "chunker": result.name,
                    "avg_tokens": result.chunk_statistics["mean_tokens"],
                    **result.overall,
                }
            )


def _pack_units(
    document: EvaluationDocument,
    units: list[tuple[str, str]],
    tokenizer: Tokenizer,
    target_tokens: int,
) -> tuple[EvaluationChunk, ...]:
    chunks: list[EvaluationChunk] = []
    current: list[tuple[str, str]] = []
    for unit in units:
        candidate = "\n\n".join(text for text, _ in (*current, unit))
        if current and tokenizer.count(candidate) > target_tokens:
            chunks.append(_make_eval_chunk(document, current, tokenizer, len(chunks)))
            current = []
        current.append(unit)
    if current:
        chunks.append(_make_eval_chunk(document, current, tokenizer, len(chunks)))
    return tuple(chunks)


def _make_eval_chunk(
    document: EvaluationDocument,
    units: list[tuple[str, str]],
    tokenizer: Tokenizer,
    index: int,
) -> EvaluationChunk:
    text = "\n\n".join(item[0] for item in units)
    return EvaluationChunk(
        text=text,
        source_block_ids=frozenset(item[1] for item in units),
        document_id=document.id,
        chunk_index=index,
        language=document.language,
        token_count=tokenizer.count(text),
    )


def _ranking_block_coverage(
    query: EvaluationQuery,
    chunks: tuple[EvaluationChunk, ...],
    chunk_embeddings: list[list[float]],
    query_embedding: list[float],
) -> list[frozenset[str]]:
    ranked = sorted(
        zip(chunks, chunk_embeddings, strict=True),
        key=lambda item: _cosine(query_embedding, item[1]),
        reverse=True,
    )
    return [chunk.source_block_ids for chunk, _ in ranked]


def _group_metrics(
    queries: tuple[EvaluationQuery, ...], rankings: list[list[frozenset[str]]], key
) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[tuple[list[frozenset[str]], frozenset[str]]]] = {}
    for query, ranking in zip(queries, rankings, strict=True):
        grouped.setdefault(key(query), []).append((ranking, query.relevant_block_ids))
    return {
        name: aggregate_rankings(
            [ranking for ranking, _ in values], [relevant for _, relevant in values]
        )
        for name, values in sorted(grouped.items())
    }


def _overlap_ratio(chunks: tuple[EvaluationChunk, ...]) -> float:
    tokenizer = Tokenizer()
    total = sum(chunk.token_count for chunk in chunks)
    overlap = 0
    for previous, current in pairwise(chunks):
        if previous.document_id != current.document_id:
            continue
        overlap += _shared_boundary_tokens(
            tokenizer.tokens(previous.text), tokenizer.tokens(current.text)
        )
    return overlap / total if total else 0.0


def _shared_boundary_tokens(previous: tuple[str, ...], current: tuple[str, ...]) -> int:
    maximum = min(len(previous), len(current))
    for size in range(maximum, 0, -1):
        if previous[-size:] == current[:size]:
            return size
    return 0


def _sentences(text: str) -> tuple[str, ...]:
    return tuple(
        part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()
    )


def _join_tokens(tokens: tuple[str, ...]) -> str:
    output = ""
    for token in tokens:
        if not output or token in ".,!?;:%)]}" or output[-1] in "([{":
            output += token
        else:
            output += f" {token}"
    return output


def _hash_vector(text: str, dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in Tokenizer().tokens(text.lower()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        vector[digest[0] % dimensions] += -1.0 if digest[1] % 2 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        if denominator
        else 0.0
    )
