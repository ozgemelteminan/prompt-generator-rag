"""Deterministic M6.3 adversarial checks over production RAG boundaries."""

import csv
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SecurityCase:
    id: str
    language: str
    category: str
    kind: str
    query: str
    document: dict[str, Any] | None
    fixture_answer: str | None


@dataclass(frozen=True)
class SecurityOutcome:
    case_id: str
    language: str
    category: str
    passed: bool
    detail: str


def load_security_dataset(path: Path) -> tuple[str, tuple[SecurityCase, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = tuple(
        SecurityCase(
            id=item["caseId"],
            language=item["language"],
            category=item["category"],
            kind=item["kind"],
            query=item["query"],
            document=item.get("document"),
            fixture_answer=item.get("fixtureAnswer"),
        )
        for item in payload["cases"]
    )
    _validate_cases(cases)
    return payload["version"], cases


def _validate_cases(cases: tuple[SecurityCase, ...]) -> None:
    ids = [case.id for case in cases]
    valid_kinds = {
        "grounded",
        "invalid_citation",
        "insufficient",
        "workspace_isolation",
        "document_scope",
        "safe_error",
    }
    if len(ids) != len(set(ids)) or not cases:
        raise ValueError("Security cases must have unique IDs.")
    for case in cases:
        if case.language not in {"tr", "en"} or case.kind not in valid_kinds:
            raise ValueError(f"Security case {case.id} is invalid.")
        if case.kind in {"grounded", "invalid_citation", "safe_error"} and (
            case.document is None or case.fixture_answer is None
        ):
            raise ValueError(
                f"Security case {case.id} requires document and fixture answer."
            )
        if case.kind == "insufficient" and case.document is None:
            raise ValueError(f"Security case {case.id} requires malicious source text.")


def run_security_evaluation(
    cases: Iterable[SecurityCase],
) -> tuple[SecurityOutcome, ...]:
    outcomes: list[SecurityOutcome] = []
    for case in cases:
        if case.kind == "grounded":
            outcomes.append(_run_grounded_case(case))
        elif case.kind == "invalid_citation":
            outcomes.append(_run_invalid_citation_case(case))
        elif case.kind == "insufficient":
            outcomes.append(_run_insufficient_case(case))
        elif case.kind == "workspace_isolation":
            outcomes.append(_run_workspace_isolation_case(case))
        elif case.kind == "document_scope":
            outcomes.append(_run_document_scope_case(case))
        else:
            outcomes.append(_run_safe_error_case(case))
    return tuple(outcomes)


def _run_grounded_case(case: SecurityCase) -> SecurityOutcome:
    service, retrieval, generation, chunk = _grounded_service(case)
    result = service.ask(query=case.query)
    assert case.document is not None
    prompt = generation.prompt
    source = result.sources[0] if result.sources else None
    passed = (
        retrieval.calls == 1
        and generation.calls == 1
        and result.answer == case.fixture_answer
        and "UNTRUSTED DATA" in prompt
        and case.document["text"] in prompt
        and "[99]" not in (result.answer or "")
        and source is not None
        and source.citation_id == 1
        and source.document_id == case.document["documentId"]
        and source.filename == case.document["filename"]
        and source.page_start == source.page_end == case.document["page"]
        and source.chunk_id == chunk.chunk_id
        and "storage" not in source.__dict__
        and "embedding" not in source.__dict__
    )
    return _outcome(
        case, passed, "Untrusted source remained data; only actual source [1] returned."
    )


def _run_invalid_citation_case(case: SecurityCase) -> SecurityOutcome:
    from app.services.rag import RagInvalidCitationError

    service, _, generation, _ = _grounded_service(case)
    try:
        service.ask(query=case.query)
    except RagInvalidCitationError:
        return _outcome(
            case,
            generation.calls == 1,
            "Invalid [99] citation was rejected without source remapping.",
        )
    return _outcome(case, False, "Invalid citation was accepted.")


def _run_insufficient_case(case: SecurityCase) -> SecurityOutcome:
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from prompt_engine.execution import ExecutionResult

    class _EmptyRetrieval:
        calls = 0

        def search(self, **_: object) -> list[object]:
            self.calls += 1
            return []

    class _Generation:
        calls = 0

        def execute(self, _: str) -> ExecutionResult:
            self.calls += 1
            return ExecutionResult(output="This must never be returned. [1]")

    retrieval = _EmptyRetrieval()
    generation = _Generation()
    result = GroundedRagService(
        retrieval_service=retrieval,  # type: ignore[arg-type]
        context_builder=ContextBuilder(max_tokens=200),
        generation_backend=generation,
    ).ask(query=case.query)
    passed = (
        result.state == "insufficient_evidence"
        and result.answer is None
        and result.sources == ()
        and retrieval.calls == 1
        and generation.calls == 0
    )
    return _outcome(case, passed, "No evidence produced no generation or citations.")


def _grounded_service(case: SecurityCase) -> tuple[Any, Any, Any, Any]:
    from app.services.context import ContextBuilder
    from app.services.rag import GroundedRagService
    from app.services.retrieval import RetrievedChunk
    from prompt_engine.execution import ExecutionResult

    assert case.document is not None and case.fixture_answer is not None
    document = case.document
    chunk = RetrievedChunk(
        chunk_id=f"{case.id}-chunk",
        document_id=document["documentId"],
        filename=document["filename"],
        chunk_index=0,
        text=document["text"],
        distance=0.1,
        similarity=0.9,
        page_start=document["page"],
        page_end=document["page"],
        section="Untrusted heading",
        heading="Untrusted heading",
        source_block_start=0,
        source_block_end=0,
    )

    class _Retrieval:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, **_: object) -> list[RetrievedChunk]:
            self.calls += 1
            return [chunk]

    class _Generation:
        def __init__(self) -> None:
            self.calls = 0
            self.prompt = ""

        def execute(self, prompt: str) -> ExecutionResult:
            self.calls += 1
            self.prompt = prompt
            return ExecutionResult(output=case.fixture_answer or "")

    retrieval = _Retrieval()
    generation = _Generation()
    return (
        GroundedRagService(
            retrieval_service=retrieval,  # type: ignore[arg-type]
            context_builder=ContextBuilder(max_tokens=2_000),
            generation_backend=generation,
        ),
        retrieval,
        generation,
        chunk,
    )


def _run_workspace_isolation_case(case: SecurityCase) -> SecurityOutcome:
    from app.repositories.documents import DocumentNotFoundError

    service, ids = _scoped_retrieval_fixture()
    results = service.search(query=case.query)
    foreign_scope = False
    try:
        service.search(query=case.query, document_ids=(ids["workspace_b"],))
    except DocumentNotFoundError:
        foreign_scope = True
    passed = (
        bool(results)
        and all(result.document_id != ids["workspace_b"] for result in results)
        and foreign_scope
    )
    return _outcome(
        case,
        passed,
        "Workspace B evidence was filtered and cannot be explicitly selected.",
    )


def _run_document_scope_case(case: SecurityCase) -> SecurityOutcome:
    service, ids = _scoped_retrieval_fixture()
    results = service.search(query=case.query, document_ids=(ids["scoped"],))
    passed = [result.document_id for result in results] == [ids["scoped"]]
    return _outcome(
        case,
        passed,
        "Explicit document scope excluded the otherwise relevant document.",
    )


def _scoped_retrieval_fixture() -> tuple[Any, dict[str, str]]:
    from app.core.caller import CallerContext
    from app.db.models import Base
    from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION
    from app.repositories.documents import DocumentRepository
    from app.repositories.retrieval import DenseRetrievalRepository
    from app.services.retrieval import DenseRetrievalService
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    class _Embedding:
        model_id = "intfloat/multilingual-e5-large-instruct"
        dimension = SELECTED_EMBEDDING_DIMENSION

        def embed_query(self, _: str) -> list[float]:
            return [1.0] + [0.0] * (self.dimension - 1)

        def embed_passages(self, _: list[str]) -> list[list[float]]:
            raise AssertionError("Security retrieval probe only embeds the query.")

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    ids = {
        "relevant": "m63-relevant",
        "scoped": "m63-scoped",
        "workspace_b": "m63-workspace-b",
    }
    _add_embedding(
        session, document_id=ids["relevant"], workspace_id="workspace-a", vector=1.0
    )
    _add_embedding(
        session, document_id=ids["scoped"], workspace_id="workspace-a", vector=0.0
    )
    _add_embedding(
        session, document_id=ids["workspace_b"], workspace_id="workspace-b", vector=1.0
    )
    return (
        DenseRetrievalService(
            caller=CallerContext("workspace-a"),
            document_repository=DocumentRepository(session),
            retrieval_repository=DenseRetrievalRepository(session),
            embedding_provider=_Embedding(),
            default_limit=5,
            max_limit=5,
            expected_dimension=SELECTED_EMBEDDING_DIMENSION,
            hnsw_ef_search=100,
        ),
        ids,
    )


def _add_embedding(
    session: Any, *, document_id: str, workspace_id: str, vector: float
) -> None:
    from app.db.models import (
        DocumentChunkRecord,
        DocumentEmbeddingRecord,
        DocumentRecord,
    )
    from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION

    chunk_id = f"{document_id}-chunk"
    session.add(
        DocumentRecord(
            id=document_id,
            workspace_id=workspace_id,
            original_filename=f"{document_id}.txt",
            media_type="text/plain",
            file_size=10,
            checksum=(document_id.replace("-", "") + "0" * 64)[:64],
            ingestion_status="embedded",
            storage_key=f"m6-security/{document_id}",
        )
    )
    session.add(
        DocumentChunkRecord(
            id=chunk_id,
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_index=0,
            text=f"Evidence in {workspace_id}",
            token_count=3,
            language="en",
            page_start=1,
            page_end=1,
            section="Security",
            heading="Security",
            source_block_start=0,
            source_block_end=0,
        )
    )
    session.add(
        DocumentEmbeddingRecord(
            id=f"{document_id}-embedding",
            workspace_id=workspace_id,
            document_id=document_id,
            chunk_id=chunk_id,
            embedding=[vector] + [0.0] * (SELECTED_EMBEDDING_DIMENSION - 1),
            embedding_model_id="intfloat/multilingual-e5-large-instruct",
            embedding_dimension=SELECTED_EMBEDDING_DIMENSION,
        )
    )
    session.commit()


def _run_safe_error_case(case: SecurityCase) -> SecurityOutcome:
    from app.services.rag import RagGenerationError
    from prompt_engine.errors import ExecutionBackendError

    service, _, _, _ = _grounded_service(case)

    class _FailingGeneration:
        def execute(self, _: str) -> object:
            raise ExecutionBackendError("provider api_key=private-value")

    service._generation_backend = _FailingGeneration()
    try:
        service.ask(query=case.query)
    except RagGenerationError as error:
        exposed = str(error).casefold()
        return _outcome(
            case,
            "private-value" not in exposed and "api_key" not in exposed,
            "Provider internals are mapped to a stable application error.",
        )
    return _outcome(case, False, "Provider error was not safely mapped.")


def _outcome(case: SecurityCase, passed: bool, detail: str) -> SecurityOutcome:
    return SecurityOutcome(case.id, case.language, case.category, passed, detail)


def aggregate_security_outcomes(outcomes: Iterable[SecurityOutcome]) -> dict[str, Any]:
    values = tuple(outcomes)
    return {
        "overall": _aggregate(values),
        "byLanguage": _group(values, lambda item: item.language),
        "byCategory": _group(values, lambda item: item.category),
    }


def _group(values: tuple[SecurityOutcome, ...], key: Any) -> dict[str, dict[str, int]]:
    grouped: defaultdict[str, list[SecurityOutcome]] = defaultdict(list)
    for value in values:
        grouped[key(value)].append(value)
    return {name: _aggregate(items) for name, items in sorted(grouped.items())}


def _aggregate(values: Iterable[SecurityOutcome]) -> dict[str, int]:
    rows = tuple(values)
    return {"passed": sum(row.passed for row in rows), "total": len(rows)}


CSV_FIELDNAMES = ("case_id", "language", "category", "passed", "detail")


def write_security_artifacts(
    outcomes: tuple[SecurityOutcome, ...], *, output_dir: Path
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "experimentVersion": "m6.3",
        "datasetVersion": "security-eval-v1",
        "status": "deterministic_fixture_run",
        "results": aggregate_security_outcomes(outcomes),
        "outcomes": [asdict(outcome) for outcome in outcomes],
        "failures": [asdict(outcome) for outcome in outcomes if not outcome.passed],
        "limitations": [
            "This deterministic suite validates application boundaries; it does not predict how every external model will react to adversarial text.",
            "Workspace/document scope uses the production service and repository with SQLite test storage; M6.1 supplies the separate pgvector smoke path.",
            "No live provider, model, or secret was used.",
        ],
    }
    (output_dir / "security_eval_v1.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (output_dir / "security_eval_v1.csv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(asdict(outcome) for outcome in outcomes)
    summary = payload["results"]
    language_rows = "\n".join(
        f"| {name} | {result['passed']} / {result['total']} |"
        for name, result in summary["byLanguage"].items()
    )
    category_rows = "\n".join(
        f"| {name} | {result['passed']} / {result['total']} |"
        for name, result in summary["byCategory"].items()
    )
    (output_dir / "security_eval_v1.md").write_text(
        "# M6.3 RAG security evaluation\n\n"
        f"Deterministic fixture result: **{summary['overall']['passed']} / {summary['overall']['total']} passed**.\n\n"
        "## By language\n\n| Language | Passed |\n| --- | ---: |\n"
        f"{language_rows}\n\n"
        "## By attack category\n\n| Category | Passed |\n| --- | ---: |\n"
        f"{category_rows}\n\n"
        "## Failures\n\n"
        + (
            "None in this run.\n"
            if not payload["failures"]
            else "\n".join(
                f"- `{item['case_id']}`: {item['detail']}"
                for item in payload["failures"]
            )
            + "\n"
        )
        + "\n## Limitations\n\n"
        + "\n".join(f"- {item}" for item in payload["limitations"])
        + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    _, _cases = load_security_dataset(Path("evals/datasets/security_eval_v1.json"))
    write_security_artifacts(
        run_security_evaluation(_cases), output_dir=Path("evals/results/final")
    )
