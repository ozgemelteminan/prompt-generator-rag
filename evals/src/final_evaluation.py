"""Build the M6.5 final report strictly from existing evaluation artifacts."""

import json
from pathlib import Path
from typing import Any

SOURCE_FILES = {
    "chunking": Path("chunking/chunking_results_v1.json"),
    "embeddings": Path("embeddings/embedding_results_v1.json"),
    "retrieval": Path("retrieval/sparse_dense_results_v1.json"),
    "hybrid": Path("hybrid/hybrid_rrf_results_v1.json"),
    "reranking": Path("reranking/reranker_results_v1.json"),
    "ablation": Path("final/m4_full_ablation_v1.json"),
    "parity": Path("final/production_rag_parity_v1.json"),
    "answer": Path("final/answer_eval_v1.json"),
    "security": Path("final/security_eval_v1.json"),
    "operational": Path("final/operational_eval_v1.json"),
}


class FinalEvaluationArtifactError(ValueError):
    """Raised when a required result artifact is missing or malformed."""


def load_source_artifacts(results_root: Path) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    for name, relative_path in SOURCE_FILES.items():
        path = results_root / relative_path
        if not path.exists():
            raise FinalEvaluationArtifactError(f"Required artifact is missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise FinalEvaluationArtifactError(f"Artifact is not a JSON object: {path}")
        artifacts[name] = payload
    return artifacts


def build_final_evaluation(artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    chunking = artifacts["chunking"]
    embeddings = artifacts["embeddings"]
    ablation = artifacts["ablation"]
    parity = artifacts["parity"]
    answer = artifacts["answer"]
    security = artifacts["security"]
    operational = artifacts["operational"]
    structure_aware = _find(chunking["results"], "name", "production_structure_aware")
    e5 = _find(embeddings["results"], "model_key", "multilingual_e5_large_instruct")
    dense = _find(ablation["ablation"], "system", "Structure-aware + E5 Dense")
    bm25 = _find(ablation["ablation"], "system", "Structure-aware + BM25")
    hybrid = _find(
        ablation["ablation"], "system", "Structure-aware + E5 Dense + BM25 + RRF"
    )
    dense_reranker = _find(ablation["ablation"], "system", "Dense + Reranker")
    hybrid_reranker = _find(ablation["ablation"], "system", "Hybrid RRF + Reranker")
    recommendation = ablation["recommendation"]
    _require(
        structure_aware["overall"]["mrr"]
        > _find(chunking["results"], "name", "fixed")["overall"]["mrr"],
        "Structure-aware chunker no longer exceeds fixed chunking MRR.",
    )
    _require(
        e5["metrics"]["mrr"]
        == max(item["metrics"]["mrr"] for item in embeddings["results"]),
        "Selected E5 model is not the measured MRR leader.",
    )
    _require(
        recommendation["selected_retrieval"] == "Dense-only", "M4 selection changed."
    )
    return {
        "reportVersion": "m6.5",
        "sources": {name: str(path) for name, path in SOURCE_FILES.items()},
        "finalArchitecture": {
            "pipeline": [
                "StructureAwareChunker(350/500/40)",
                "intfloat/multilingual-e5-large-instruct",
                "PostgreSQL + pgvector dense retrieval",
                "Context Builder",
                "grounded generation",
                "citation validation",
            ],
            "selectionEvidence": {
                "structure_aware_mrr": structure_aware["overall"]["mrr"],
                "fixed_chunking_mrr": _find(chunking["results"], "name", "fixed")[
                    "overall"
                ]["mrr"],
                "e5_mrr": e5["metrics"]["mrr"],
                "dense_mrr": dense["metrics"]["mrr"],
                "hybrid_mrr": hybrid["metrics"]["mrr"],
                "dense_reranker_recall_at_5": dense_reranker["metrics"]["recall_at_5"],
                "dense_recall_at_5": dense["metrics"]["recall_at_5"],
            },
            "decisions": {
                "dense_default": recommendation["rrf_decision"],
                "reranker": recommendation["reranker_decision"],
            },
        },
        "realExperimentalResults": {
            "classification": "M4 benchmark/model results from committed official artifacts.",
            "chunking": [_chunking_row(item) for item in chunking["results"]],
            "embeddings": [_embedding_row(item) for item in embeddings["results"]],
            "retrievalAblation": [
                _ablation_row(item)
                for item in (dense, bm25, hybrid, dense_reranker, hybrid_reranker)
            ],
        },
        "deterministicHarnessValidation": {
            "parity": {
                "status": parity["status"],
                "passed_checks": sum(check["passed"] for check in parity["checks"]),
                "total_checks": len(parity["checks"]),
            },
            "answerCitation": {
                "status": answer["status"],
                "overall": answer["metrics"]["overall"],
            },
            "security": {
                "status": security["status"],
                "overall": security["results"]["overall"],
            },
            "operational": {
                "local_status": operational["deterministicLocal"]["status"],
                "successful_ask": operational["deterministicLocal"]["successfulAsk"],
                "insufficient_evidence": operational["deterministicLocal"][
                    "insufficientEvidence"
                ],
                "latency": operational["deterministicLocal"]["latency"],
                "token_cost": operational["deterministicLocal"]["tokenCost"],
            },
        },
        "pendingOptInRuns": {
            "pgvector_smoke": parity["postgresPgvectorSmoke"],
            "answer_provider_run": answer["status"] != "provider_run",
            "operational_real_run": operational["realRun"],
        },
        "limitations": [
            "M6 answer/citation scores are fixture-only unless an explicit provider run replaces that status.",
            "The pgvector smoke test is opt-in and remains unexecuted when its artifact status is not_run.",
            "M6 operational timings are local fixture measurements, not production latency targets.",
            "The current provider-neutral execution adapter exposes no real provider token/cost metadata.",
            "M6 security validation proves deterministic boundaries, not universal live-model prompt-injection robustness.",
            "The reviewed retrieval corpus contains 84 Turkish/English queries and is not representative production traffic.",
        ],
    }


def _find(rows: list[dict[str, Any]], field: str, value: str) -> dict[str, Any]:
    for row in rows:
        if row.get(field) == value:
            return row
    raise FinalEvaluationArtifactError(f"Expected {field}={value!r} is missing.")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalEvaluationArtifactError(message)


def _chunking_row(item: dict[str, Any]) -> dict[str, Any]:
    return {"name": item["name"], **item["overall"]}


def _embedding_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_key": item["model_key"],
        "model_id": item["model_id"],
        **item["metrics"],
    }


def _ablation_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "system": item["system"],
        **item["metrics"],
        "tr_mrr": item["tr_mrr"],
        "en_mrr": item["en_mrr"],
    }


def write_final_evaluation(report: dict[str, Any], *, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "final_evaluation_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    architecture = report["finalArchitecture"]
    real = report["realExperimentalResults"]
    validation = report["deterministicHarnessValidation"]
    (output_dir / "final_evaluation_v1.md").write_text(
        "# Final evaluation report\n\n"
        "## Evidence classification\n\n"
        "- **Real experimental/model results:** M4 benchmark artifacts below.\n"
        "- **Deterministic fixture/harness validation:** M6 statuses below; these are not live-model quality scores.\n"
        "- **Pending opt-in runs:** PostgreSQL/pgvector smoke, live answer-provider evaluation, and real operational timing.\n\n"
        "## Selected production RAG architecture\n\n"
        + " → ".join(architecture["pipeline"])
        + "\n\n"
        "Structure-aware chunking improved MRR from "
        f"{architecture['selectionEvidence']['fixed_chunking_mrr']:.3f} to {architecture['selectionEvidence']['structure_aware_mrr']:.3f}. "
        f"E5 was the measured embedding MRR leader ({architecture['selectionEvidence']['e5_mrr']:.3f}). "
        "Dense-only remains the default because Hybrid RRF added only a small ranking gain without recall gain or a recovered Dense miss; "
        "the tested reranker reduced Recall@5 and nDCG@10.\n\n"
        "## M4 real experimental results\n\n"
        "### Chunking\n\n| Chunker | Recall@5 | Recall@10 | MRR | nDCG@10 |\n| --- | ---: | ---: | ---: | ---: |\n"
        + "\n".join(_format_row(row, "name") for row in real["chunking"])
        + "\n\n### Embeddings\n\n| Model | Recall@10 | MRR | nDCG@10 | Block coverage@10 |\n| --- | ---: | ---: | ---: | ---: |\n"
        + "\n".join(_format_embedding_row(row) for row in real["embeddings"])
        + "\n\n### Dense, sparse, Hybrid, and Reranker ablation\n\n| System | Recall@5 | Recall@10 | MRR | nDCG@10 | TR MRR | EN MRR |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n"
        + "\n".join(_format_ablation_row(row) for row in real["retrievalAblation"])
        + "\n\n## M6 deterministic fixture/harness validation\n\n"
        "| Area | Evidence kind | Status | Result |\n| --- | --- | --- | --- |\n"
        f"| Production parity | deterministic harness | {validation['parity']['status']} | {validation['parity']['passed_checks']}/{validation['parity']['total_checks']} checks; pgvector smoke {report['pendingOptInRuns']['pgvector_smoke']['status']} |\n"
        f"| Answer/citation | fixture harness | {validation['answerCitation']['status']} | Not a live-model quality result |\n"
        f"| Security | deterministic harness | {validation['security']['status']} | {validation['security']['overall']['passed']}/{validation['security']['overall']['total']} cases |\n"
        f"| Operational | local fixture | {validation['operational']['local_status']} | Real run {report['pendingOptInRuns']['operational_real_run']['status']} |\n\n"
        "## Limitations\n\n"
        + "\n".join(f"- {item}" for item in report["limitations"])
        + "\n",
        encoding="utf-8",
    )


def _format_row(row: dict[str, Any], name: str) -> str:
    return "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
        row[name],
        row["recall_at_5"],
        row["recall_at_10"],
        row["mrr"],
        row["ndcg_at_10"],
    )


def _format_embedding_row(row: dict[str, Any]) -> str:
    return "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
        row["model_id"],
        row["recall_at_10"],
        row["mrr"],
        row["ndcg_at_10"],
        row["required_block_coverage_at_10"],
    )


def _format_ablation_row(row: dict[str, Any]) -> str:
    return "| {} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} | {:.3f} |".format(
        row["system"],
        row["recall_at_5"],
        row["recall_at_10"],
        row["mrr"],
        row["ndcg_at_10"],
        row["tr_mrr"],
        row["en_mrr"],
    )


if __name__ == "__main__":
    _root = Path("evals/results")
    write_final_evaluation(
        build_final_evaluation(load_source_artifacts(_root)), output_dir=_root / "final"
    )
