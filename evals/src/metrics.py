"""Centralized ranking metrics for M4 and later retrieval experiments."""

import math
from collections.abc import Sequence


def is_relevant(
    source_block_ids: frozenset[str], relevant_block_ids: frozenset[str]
) -> bool:
    """A chunk is relevant when its source-block coverage intersects ground truth."""
    return bool(source_block_ids & relevant_block_ids)


def recall_at_k(
    retrieved_block_ids: Sequence[frozenset[str]],
    relevant_block_ids: frozenset[str],
    k: int,
) -> float:
    if not relevant_block_ids:
        return 0.0
    covered = (
        set().union(*retrieved_block_ids[:k]) if retrieved_block_ids[:k] else set()
    )
    return len(covered & relevant_block_ids) / len(relevant_block_ids)


def hit_rate_at_k(
    retrieved_block_ids: Sequence[frozenset[str]],
    relevant_block_ids: frozenset[str],
    k: int,
) -> float:
    return float(
        any(
            is_relevant(block_ids, relevant_block_ids)
            for block_ids in retrieved_block_ids[:k]
        )
    )


def required_block_coverage_at_k(
    retrieved_block_ids: Sequence[frozenset[str]],
    required_block_ids: frozenset[str],
    k: int,
) -> float:
    """Share of required source blocks represented by the top-k retrieved chunks."""
    return recall_at_k(retrieved_block_ids, required_block_ids, k)


def reciprocal_rank(
    retrieved_block_ids: Sequence[frozenset[str]], relevant_block_ids: frozenset[str]
) -> float:
    for index, block_ids in enumerate(retrieved_block_ids, start=1):
        if is_relevant(block_ids, relevant_block_ids):
            return 1.0 / index
    return 0.0


def ndcg_at_k(
    retrieved_block_ids: Sequence[frozenset[str]],
    relevant_block_ids: frozenset[str],
    k: int,
) -> float:
    dcg = sum(
        1.0 / math.log2(index + 1)
        for index, block_ids in enumerate(retrieved_block_ids[:k], start=1)
        if is_relevant(block_ids, relevant_block_ids)
    )
    ideal_count = min(len(relevant_block_ids), k)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_count + 1))
    return dcg / ideal if ideal else 0.0


def aggregate_rankings(
    rankings: Sequence[Sequence[frozenset[str]]],
    relevant_sets: Sequence[frozenset[str]],
) -> dict[str, float]:
    if not rankings:
        return {
            "recall_at_5": 0.0,
            "recall_at_10": 0.0,
            "hit_rate_at_5": 0.0,
            "mrr": 0.0,
            "ndcg_at_10": 0.0,
        }
    count = len(rankings)
    return {
        "recall_at_5": sum(
            recall_at_k(ranking, relevant, 5)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / count,
        "recall_at_10": sum(
            recall_at_k(ranking, relevant, 10)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / count,
        "hit_rate_at_5": sum(
            hit_rate_at_k(ranking, relevant, 5)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / count,
        "mrr": sum(
            reciprocal_rank(ranking, relevant)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / count,
        "ndcg_at_10": sum(
            ndcg_at_k(ranking, relevant, 10)
            for ranking, relevant in zip(rankings, relevant_sets, strict=True)
        )
        / count,
    }
