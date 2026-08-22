import json
import sys
from pathlib import Path

import pytest

from evals.src.operational_eval import (
    PriceAssumption,
    TimingCollector,
    TokenUsage,
    aggregate_token_usage,
    run_deterministic_local,
    summarize_latency,
    write_operational_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]


def _configure_production_imports() -> None:
    sys.path.insert(0, str(ROOT / "apps/api"))
    sys.path.insert(0, str(ROOT / "packages/prompt-engine"))


def test_latency_summary_uses_nearest_rank_p50_and_p95() -> None:
    assert summarize_latency([]) == {
        "count": 0,
        "mean_ms": None,
        "p50_ms": None,
        "p95_ms": None,
        "min_ms": None,
        "max_ms": None,
    }
    summary = summarize_latency([5.0, 1.0, 3.0, 2.0, 4.0])
    assert summary == {
        "count": 5,
        "mean_ms": 3.0,
        "p50_ms": 3.0,
        "p95_ms": 5.0,
        "min_ms": 1.0,
        "max_ms": 5.0,
    }


def test_timing_collector_records_operation_duration_with_injected_clock() -> None:
    values = iter((10.0, 10.025))
    collector = TimingCollector(clock=lambda: next(values))

    assert collector.measure("phase", lambda: "result") == "result"
    assert collector.values["phase"][0] == pytest.approx(25.0)


def test_token_and_cost_summary_requires_explicit_price_and_known_tokens() -> None:
    price = PriceAssumption(2.0, 6.0, "USD", "2026-08-22")
    known = aggregate_token_usage([TokenUsage(1_000, 500, 1)], price=price)
    unknown = aggregate_token_usage([TokenUsage(None, None, 1)], price=price)

    assert known["total_tokens"] == 1_500
    assert known["estimated_cost"] == 0.005
    assert known["currency"] == "USD"
    assert unknown["estimated_cost"] is unknown["total_tokens"] is None


def test_local_operational_path_preserves_request_count_and_no_generation_on_insufficient(
    tmp_path: Path,
) -> None:
    _configure_production_imports()
    local = run_deterministic_local()
    payload = write_operational_artifacts(local, output_dir=tmp_path)

    assert local["successfulAsk"] == {
        "query_embedding_calls": 1,
        "retrieval_calls": 1,
        "context_build_calls": 1,
        "generation_calls": 1,
        "passed": True,
    }
    assert local["insufficientEvidence"]["generation_calls"] == 0
    assert all(local["operationalChecks"].values())
    assert local["tokenCost"]["total_tokens"] is None
    assert payload["realRun"]["status"] == "not_run"
    assert (
        json.loads((tmp_path / "operational_eval_v1.json").read_text())[
            "deterministicLocal"
        ]
        == local
    )
    assert (tmp_path / "operational_eval_v1.csv").read_text().startswith("phase,")
