import json
from pathlib import Path

import pytest

from evals.src.final_evaluation import (
    SOURCE_FILES,
    FinalEvaluationArtifactError,
    build_final_evaluation,
    load_source_artifacts,
    write_final_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = ROOT / "evals/results"


def test_final_evaluation_references_all_required_source_artifacts() -> None:
    artifacts = load_source_artifacts(RESULTS_ROOT)

    assert set(artifacts) == set(SOURCE_FILES)
    assert all((RESULTS_ROOT / path).exists() for path in SOURCE_FILES.values())


def test_final_evaluation_copies_metrics_and_statuses_from_sources(
    tmp_path: Path,
) -> None:
    artifacts = load_source_artifacts(RESULTS_ROOT)
    report = build_final_evaluation(artifacts)
    write_final_evaluation(report, output_dir=tmp_path)

    chunker = next(
        item
        for item in artifacts["chunking"]["results"]
        if item["name"] == "production_structure_aware"
    )
    embedding = next(
        item
        for item in artifacts["embeddings"]["results"]
        if item["model_key"] == "multilingual_e5_large_instruct"
    )
    assert (
        report["finalArchitecture"]["selectionEvidence"]["structure_aware_mrr"]
        == chunker["overall"]["mrr"]
    )
    assert (
        report["finalArchitecture"]["selectionEvidence"]["e5_mrr"]
        == embedding["metrics"]["mrr"]
    )
    assert report["deterministicHarnessValidation"]["parity"]["status"] == "passed"
    assert (
        report["deterministicHarnessValidation"]["answerCitation"]["status"]
        == "fixture_only"
    )
    assert report["pendingOptInRuns"]["pgvector_smoke"]["status"] == "not_run"
    assert json.loads((tmp_path / "final_evaluation_v1.json").read_text()) == report
    markdown = (tmp_path / "final_evaluation_v1.md").read_text()
    assert "fixture-only" in markdown
    assert "Pending opt-in runs" in markdown


def test_final_evaluation_rejects_missing_source_artifact(tmp_path: Path) -> None:
    with pytest.raises(FinalEvaluationArtifactError, match="missing"):
        load_source_artifacts(tmp_path)
