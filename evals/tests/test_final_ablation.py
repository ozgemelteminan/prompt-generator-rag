import json
from pathlib import Path

import pytest

from evals.src.final_ablation import (
    OfficialArtifactError,
    build_ablation_rows,
    build_recommendation,
    load_official_artifacts,
    write_final_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]


def test_loads_all_committed_official_artifacts() -> None:
    artifacts = load_official_artifacts(ROOT / "evals/results")
    assert set(artifacts) == {
        "chunking",
        "embeddings",
        "retrieval",
        "hybrid",
        "reranking",
    }


def test_rejects_placeholder_artifact(tmp_path) -> None:
    for relative_path in (
        "chunking/chunking_results_v1.json",
        "embeddings/embedding_results_v1.json",
        "retrieval/sparse_dense_results_v1.json",
        "hybrid/hybrid_rrf_results_v1.json",
        "reranking/reranker_results_v1.json",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"status": "requires_real_model_run"}')
    with pytest.raises(OfficialArtifactError, match="lacks official"):
        load_official_artifacts(tmp_path)


def test_ablation_marks_missing_cross_stage_metrics_unavailable() -> None:
    rows = build_ablation_rows(load_official_artifacts(ROOT / "evals/results"))
    assert len(rows) == 7
    assert rows[0].metrics["required_block_coverage_at_5"] is None
    assert rows[2].metrics["required_block_coverage_at_10"] == 1.0


def test_recommendation_uses_measured_deltas_and_excludes_tested_reranker() -> None:
    recommendation = build_recommendation(
        load_official_artifacts(ROOT / "evals/results")
    )
    assert recommendation.selected_retrieval == "Dense-only"
    assert recommendation.deltas["hybrid_vs_dense_mrr"] > 0
    assert recommendation.deltas["hybrid_vs_dense_recall_at_10"] == 0
    assert recommendation.deltas["dense_reranker_vs_dense_recall_at_5"] < 0
    assert "Exclude BAAI/bge-reranker-v2-m3" in recommendation.reranker_decision


def test_final_artifacts_serialize_rows_and_recommendation(tmp_path) -> None:
    artifacts = load_official_artifacts(ROOT / "evals/results")
    rows = build_ablation_rows(artifacts)
    recommendation = build_recommendation(artifacts)
    write_final_artifacts(rows, recommendation, output_dir=tmp_path)

    payload = json.loads((tmp_path / "m4_full_ablation_v1.json").read_text())
    assert len(payload["ablation"]) == 7
    assert (tmp_path / "m4_full_ablation_v1.csv").read_text().startswith("system,")
    assert "Reranker decision" in (tmp_path / "m4_recommendation_v1.md").read_text()
