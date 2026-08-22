"""M4.6 artifact-only ablation consolidation and recommendation generation."""

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

METRIC_FIELDS = (
    "recall_at_5",
    "recall_at_10",
    "mrr",
    "ndcg_at_10",
    "hit_rate_at_5",
    "required_block_coverage_at_5",
    "required_block_coverage_at_10",
)
CSV_FIELDNAMES = (
    "system",
    "source_artifact",
    *METRIC_FIELDS,
    "tr_mrr",
    "en_mrr",
)
REQUIRED_ARTIFACTS = {
    "chunking": Path("chunking/chunking_results_v1.json"),
    "embeddings": Path("embeddings/embedding_results_v1.json"),
    "retrieval": Path("retrieval/sparse_dense_results_v1.json"),
    "hybrid": Path("hybrid/hybrid_rrf_results_v1.json"),
    "reranking": Path("reranking/reranker_results_v1.json"),
}


class OfficialArtifactError(ValueError):
    """Raised when a required M4 result is absent, placeholder, or malformed."""


@dataclass(frozen=True)
class AblationRow:
    system: str
    source_artifact: str
    metrics: dict[str, float | None]
    tr_mrr: float | None
    en_mrr: float | None


@dataclass(frozen=True)
class Recommendation:
    selected_retrieval: str
    rrf_decision: str
    reranker_decision: str
    deltas: dict[str, float | None]
    limitations: tuple[str, ...]


def load_official_artifacts(results_root: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, relative_path in REQUIRED_ARTIFACTS.items():
        path = results_root / relative_path
        if not path.exists():
            raise OfficialArtifactError(f"Required artifact is missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") == "requires_real_model_run" or not payload.get(
            "results"
        ):
            raise OfficialArtifactError(
                f"Artifact lacks official real-model results: {path}"
            )
        artifacts[name] = payload
    return artifacts


def build_ablation_rows(artifacts: dict[str, dict[str, Any]]) -> list[AblationRow]:
    chunking = artifacts["chunking"]
    embeddings = artifacts["embeddings"]
    retrieval = artifacts["retrieval"]
    hybrid = artifacts["hybrid"]
    reranking = artifacts["reranking"]
    _require_result(chunking, "name", "fixed")
    _require_result(chunking, "name", "production_structure_aware")
    _require_result(embeddings, "model_key", "multilingual_e5_large_instruct")
    return [
        _row(
            "Fixed chunking + GTE",
            "m4.1/chunking",
            _require_result(chunking, "name", "fixed"),
        ),
        _row(
            "Structure-aware chunking + GTE",
            "m4.1/chunking",
            _require_result(chunking, "name", "production_structure_aware"),
        ),
        _row(
            "Structure-aware + E5 Dense",
            "m4.3/retrieval",
            _require_result(retrieval, "retriever_key", "dense_e5"),
        ),
        _row(
            "Structure-aware + BM25",
            "m4.3/retrieval",
            _require_result(retrieval, "retriever_key", "sparse_bm25"),
        ),
        _row(
            "Structure-aware + E5 Dense + BM25 + RRF",
            "m4.4/hybrid",
            _require_result(hybrid, "retriever_key", "hybrid_rrf"),
        ),
        _row(
            "Dense + Reranker",
            "m4.5/reranking",
            _require_result(reranking, "retriever_key", "dense_reranker"),
        ),
        _row(
            "Hybrid RRF + Reranker",
            "m4.5/reranking",
            _require_result(reranking, "retriever_key", "hybrid_reranker"),
        ),
    ]


def build_recommendation(artifacts: dict[str, dict[str, Any]]) -> Recommendation:
    embeddings = artifacts["embeddings"]
    retrieval = artifacts["retrieval"]
    hybrid = artifacts["hybrid"]
    reranking = artifacts["reranking"]
    e5 = _require_result(embeddings, "model_key", "multilingual_e5_large_instruct")
    if _metric(e5, "mrr") < max(
        _metric(result, "mrr") for result in embeddings["results"]
    ):
        raise OfficialArtifactError(
            "M4.2 selected embedding is not the measured MRR leader."
        )
    dense = _require_result(retrieval, "retriever_key", "dense_e5")
    hybrid_result = _require_result(hybrid, "retriever_key", "hybrid_rrf")
    dense_reranker = _require_result(reranking, "retriever_key", "dense_reranker")
    hybrid_reranker = _require_result(reranking, "retriever_key", "hybrid_reranker")
    hybrid_diagnostics = hybrid.get("diagnostics", {})
    deltas = {
        "hybrid_vs_dense_mrr": _metric(hybrid_result, "mrr") - _metric(dense, "mrr"),
        "hybrid_vs_dense_ndcg_at_10": _metric(hybrid_result, "ndcg_at_10")
        - _metric(dense, "ndcg_at_10"),
        "hybrid_vs_dense_recall_at_10": _metric(hybrid_result, "recall_at_10")
        - _metric(dense, "recall_at_10"),
        "hybrid_vs_dense_tr_mrr": _language_metric(hybrid_result, "tr", "mrr")
        - _language_metric(dense, "tr", "mrr"),
        "hybrid_vs_dense_en_mrr": _language_metric(hybrid_result, "en", "mrr")
        - _language_metric(dense, "en", "mrr"),
        "dense_reranker_vs_dense_recall_at_5": _metric(dense_reranker, "recall_at_5")
        - _metric(dense, "recall_at_5"),
        "dense_reranker_vs_dense_ndcg_at_10": _metric(dense_reranker, "ndcg_at_10")
        - _metric(dense, "ndcg_at_10"),
        "hybrid_reranker_vs_hybrid_recall_at_5": _metric(hybrid_reranker, "recall_at_5")
        - _metric(hybrid_result, "recall_at_5"),
    }
    no_new_dense_misses = not hybrid_diagnostics.get("hybrid_recovers_dense_miss")
    unchanged_recall = deltas["hybrid_vs_dense_recall_at_10"] == 0
    selected_retrieval = (
        "Dense-only"
        if unchanged_recall and no_new_dense_misses
        else "Hybrid RRF requires a larger validation before default selection"
    )
    reranker_degrades = (
        deltas["dense_reranker_vs_dense_recall_at_5"] < 0
        and deltas["dense_reranker_vs_dense_ndcg_at_10"] < 0
    )
    return Recommendation(
        selected_retrieval=selected_retrieval,
        rrf_decision=(
            "Do not make RRF the M5 default: the measured ranking gain is small, recall is unchanged, and no Dense miss was recovered."
            if selected_retrieval == "Dense-only"
            else "Validate Hybrid RRF on a larger benchmark before choosing a default."
        ),
        reranker_decision=(
            "Exclude BAAI/bge-reranker-v2-m3 from M5: this tested configuration reduced Recall@5 and nDCG@10."
            if reranker_degrades
            else "Reranker evidence is inconclusive; do not include it without further evaluation."
        ),
        deltas=deltas,
        limitations=(
            "retrieval_eval_v1 has 84 manually reviewable Turkish/English queries; it is not a production traffic sample.",
            "Ground truth uses source-block relevance, which can create recall ceilings and does not measure answer quality.",
            "No production latency or cost benchmark has been run.",
            "BM25 has no Turkish morphology or stemming analyzer.",
            "Only BAAI/bge-reranker-v2-m3 was tested; this does not generalize to all rerankers.",
            "No statistical significance analysis was performed.",
        ),
    )


def write_final_artifacts(
    rows: list[AblationRow], recommendation: Recommendation, *, output_dir: Path
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m4.6",
        "ablation": [asdict(row) for row in rows],
        "recommendation": asdict(recommendation),
    }
    (output_dir / "m4_full_ablation_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (output_dir / "m4_full_ablation_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(_csv_row(row) for row in rows)
    (output_dir / "m4_recommendation_v1.md").write_text(
        render_recommendation(recommendation), encoding="utf-8"
    )


def render_recommendation(recommendation: Recommendation) -> str:
    deltas = recommendation.deltas
    return f"""# M4 final recommendation

## 1. Selected chunker

Production `StructureAwareChunker`: target 350, maximum 500, overlap 40 tokens.

## 2. Selected embedding

`intfloat/multilingual-e5-large-instruct`.

## 3. Selected retrieval architecture

{recommendation.selected_retrieval}: StructureAwareChunker → multilingual E5 → dense retrieval.

## 4. RRF decision

{recommendation.rrf_decision}

Measured Hybrid − Dense: MRR {deltas["hybrid_vs_dense_mrr"]:+.4f}; nDCG@10 {deltas["hybrid_vs_dense_ndcg_at_10"]:+.4f}; Recall@10 {deltas["hybrid_vs_dense_recall_at_10"]:+.4f}; TR MRR {deltas["hybrid_vs_dense_tr_mrr"]:+.4f}; EN MRR {deltas["hybrid_vs_dense_en_mrr"]:+.4f}.

## 5. Reranker decision

{recommendation.reranker_decision}

This conclusion is limited to the tested candidate depth, dataset, and configuration; it does not claim that reranking never works.

## 6. Exact M5 configuration

StructureAwareChunker (350/500/40) → multilingual-e5-large-instruct → dense retrieval. Keep BM25/RRF behind evaluation-only validation, and do not include the tested reranker.

## 7. Evidence summary

E5 was the measured M4.2 MRR leader. Dense E5 beat standalone BM25 in M4.3. M4.4 Hybrid improved ranking metrics slightly but did not improve recall or recover a Dense miss; without production latency evidence, the simpler Dense default is the defensible choice.

## 8. Known limitations

{chr(10).join(f"- {item}" for item in recommendation.limitations)}

## 9. What M5 should implement

Production support for the selected Dense configuration, plus measurement hooks and a larger held-out evaluation before reconsidering Hybrid RRF.

## 10. What M5 should NOT implement

Do not ship the tested reranker, production BM25/RRF, query rewriting, context building, citations, or generation solely from these M4 results.
"""


def _row(system: str, source_artifact: str, result: dict[str, Any]) -> AblationRow:
    return AblationRow(
        system=system,
        source_artifact=source_artifact,
        metrics={field: _optional_metric(result, field) for field in METRIC_FIELDS},
        tr_mrr=_optional_language_metric(result, "tr", "mrr"),
        en_mrr=_optional_language_metric(result, "en", "mrr"),
    )


def _require_result(payload: dict[str, Any], field: str, value: str) -> dict[str, Any]:
    for result in payload["results"]:
        if result.get(field) == value:
            return result
    raise OfficialArtifactError(f"Required result {field}={value!r} is absent.")


def _metric(result: dict[str, Any], field: str) -> float:
    value = _optional_metric(result, field)
    if value is None:
        raise OfficialArtifactError(f"Required metric {field!r} is absent.")
    return value


def _optional_metric(result: dict[str, Any], field: str) -> float | None:
    metrics = result.get("metrics", result.get("overall", {}))
    value = metrics.get(field)
    return float(value) if value is not None else None


def _language_metric(result: dict[str, Any], language: str, field: str) -> float:
    value = _optional_language_metric(result, language, field)
    if value is None:
        raise OfficialArtifactError(f"Required {language} metric {field!r} is absent.")
    return value


def _optional_language_metric(
    result: dict[str, Any], language: str, field: str
) -> float | None:
    value = result.get("by_language", {}).get(language, {}).get(field)
    return float(value) if value is not None else None


def _csv_row(row: AblationRow) -> dict[str, str | float | None]:
    return {
        "system": row.system,
        "source_artifact": row.source_artifact,
        **row.metrics,
        "tr_mrr": row.tr_mrr,
        "en_mrr": row.en_mrr,
    }
