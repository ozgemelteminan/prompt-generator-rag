import math

import pytest

from evals.src.metrics import (
    aggregate_rankings,
    hit_rate_at_k,
    is_relevant,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_block_intersection_defines_chunk_relevance() -> None:
    assert is_relevant(frozenset({"block-1", "block-2"}), frozenset({"block-2"}))
    assert not is_relevant(frozenset({"block-1"}), frozenset({"block-3"}))


def test_ranking_metric_formulas() -> None:
    relevant = frozenset({"b1", "b2"})
    ranking = [frozenset(), frozenset({"b1"}), frozenset(), frozenset({"b2"})]

    assert recall_at_k(ranking, relevant, 1) == 0.0
    assert (
        recall_at_k(ranking, relevant, 5) == hit_rate_at_k(ranking, relevant, 5) == 1.0
    )
    assert reciprocal_rank(ranking, relevant) == 0.5
    assert ndcg_at_k(ranking, relevant, 4) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3))
    )


def test_aggregate_rankings_averages_queries() -> None:
    metrics = aggregate_rankings(
        [[frozenset({"b1"})], [frozenset()]], [frozenset({"b1"}), frozenset({"b2"})]
    )
    assert metrics["recall_at_5"] == 0.5
    assert metrics["mrr"] == 0.5
