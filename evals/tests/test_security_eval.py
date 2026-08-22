import sys
from pathlib import Path

from evals.src.security_eval import (
    aggregate_security_outcomes,
    load_security_dataset,
    run_security_evaluation,
    write_security_artifacts,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "evals/datasets/security_eval_v1.json"


def _configure_production_imports() -> None:
    sys.path.insert(0, str(ROOT / "apps/api"))
    sys.path.insert(0, str(ROOT / "packages/prompt-engine"))


def test_security_dataset_is_small_bilingual_and_adversarial() -> None:
    version, cases = load_security_dataset(DATASET_PATH)

    assert version == "security-eval-v1"
    assert len(cases) == 10
    assert sum(case.language == "tr" for case in cases) == 5
    assert sum(case.language == "en" for case in cases) == 5
    assert {case.category for case in cases} >= {
        "prompt_injection",
        "citation_fabrication",
        "workspace_isolation",
        "document_scope",
        "insufficient_evidence",
    }


def test_security_evaluation_enforces_grounding_isolation_and_safe_errors(
    tmp_path: Path,
) -> None:
    _configure_production_imports()
    _, cases = load_security_dataset(DATASET_PATH)
    outcomes = run_security_evaluation(cases)
    payload = write_security_artifacts(outcomes, output_dir=tmp_path)

    assert len(outcomes) == 10
    assert all(outcome.passed for outcome in outcomes)
    assert aggregate_security_outcomes(outcomes) == payload["results"]
    assert payload["results"]["overall"] == {"passed": 10, "total": 10}
    assert payload["results"]["byLanguage"]["tr"] == {"passed": 5, "total": 5}
    assert "Invalid [99] citation was rejected" in next(
        outcome.detail
        for outcome in outcomes
        if outcome.case_id == "m63-en-invalid-citation"
    )
    assert (tmp_path / "security_eval_v1.csv").read_text().startswith("case_id,")
    assert "10 / 10 passed" in (tmp_path / "security_eval_v1.md").read_text()


def test_security_fixture_is_repeatable_without_provider_or_model_calls() -> None:
    _configure_production_imports()
    _, cases = load_security_dataset(DATASET_PATH)

    assert run_security_evaluation(cases) == run_security_evaluation(cases)
