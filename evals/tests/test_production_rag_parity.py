import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
sys.path.insert(0, str(ROOT / "packages/prompt-engine"))

from evals.src.production_rag_parity import (
    collect_production_parity,
    write_production_parity_artifacts,
)


def test_production_rag_parity_uses_production_boundaries_without_model_downloads() -> (
    None
):
    payload = collect_production_parity()

    assert payload["status"] == "passed"
    assert payload["productionConfiguration"]["chunker"] == {
        "implementation": "app.document_processing.chunking.StructureAwareChunker",
        "targetTokens": 350,
        "maxTokens": 500,
        "overlapTokens": 40,
    }
    assert payload["productionConfiguration"]["embedding"] == {
        "modelId": "intfloat/multilingual-e5-large-instruct",
        "dimension": 1024,
        "passageFormat": "raw_text",
        "queryFormat": (
            "Instruct: Given a web search query, retrieve relevant passages that answer the query"
            "\\nQuery: <query>"
        ),
        "normalizeEmbeddings": True,
    }
    assert all(check["passed"] for check in payload["checks"])
    assert payload["postgresPgvectorSmoke"]["status"] == "not_run"


def test_production_rag_parity_artifacts_are_serialized(tmp_path: Path) -> None:
    payload = write_production_parity_artifacts(tmp_path)

    assert (
        json.loads((tmp_path / "production_rag_parity_v1.json").read_text()) == payload
    )
    summary = (tmp_path / "production_rag_parity_v1.md").read_text()
    assert "RUN_PGVECTOR_SMOKE=1" in summary
    assert "PASS" in summary
