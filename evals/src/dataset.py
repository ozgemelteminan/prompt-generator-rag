"""Static block-based evaluation dataset loading and validation."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvaluationBlock:
    id: str
    text: str
    block_type: str
    order_index: int
    section: str | None = None
    page_number: int | None = None


@dataclass(frozen=True)
class EvaluationDocument:
    id: str
    language: str
    blocks: tuple[EvaluationBlock, ...]


@dataclass(frozen=True)
class EvaluationQuery:
    id: str
    document_id: str
    language: str
    text: str
    relevant_block_ids: frozenset[str]
    category: str


@dataclass(frozen=True)
class EvaluationDataset:
    version: str
    documents: tuple[EvaluationDocument, ...]
    queries: tuple[EvaluationQuery, ...]


def load_dataset(path: Path) -> EvaluationDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    documents = tuple(
        _load_document(path.parent / item["path"], item["documentId"], item["language"])
        for item in raw["documents"]
    )
    queries = tuple(
        EvaluationQuery(
            id=item["queryId"],
            document_id=item["documentId"],
            language=item["language"],
            text=item["query"],
            relevant_block_ids=frozenset(item["relevantBlockIds"]),
            category=item["category"],
        )
        for item in raw["queries"]
    )
    dataset = EvaluationDataset(raw["version"], documents, queries)
    validate_dataset(dataset)
    return dataset


def validate_dataset(dataset: EvaluationDataset) -> None:
    document_ids = [document.id for document in dataset.documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("Document IDs must be unique.")
    by_id = {document.id: document for document in dataset.documents}
    query_ids = [query.id for query in dataset.queries]
    if len(query_ids) != len(set(query_ids)):
        raise ValueError("Query IDs must be unique.")
    for document in dataset.documents:
        block_ids = [block.id for block in document.blocks]
        if not block_ids or len(block_ids) != len(set(block_ids)):
            raise ValueError(f"Document {document.id} has invalid block IDs.")
        if [block.order_index for block in document.blocks] != list(
            range(len(document.blocks))
        ):
            raise ValueError(f"Document {document.id} block order must be sequential.")
    for query in dataset.queries:
        document = by_id.get(query.document_id)
        if document is None:
            raise ValueError(f"Query {query.id} references an unknown document.")
        if query.language != document.language:
            raise ValueError(f"Query {query.id} language does not match its document.")
        known_blocks = {block.id for block in document.blocks}
        if not query.relevant_block_ids or not query.relevant_block_ids <= known_blocks:
            raise ValueError(f"Query {query.id} has invalid relevant block IDs.")


def _load_document(path: Path, document_id: str, language: str) -> EvaluationDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw["documentId"] != document_id or raw["language"] != language:
        raise ValueError(f"Dataset manifest and {path.name} disagree.")
    return EvaluationDocument(
        id=document_id,
        language=language,
        blocks=tuple(
            EvaluationBlock(
                id=item["id"],
                text=item["text"],
                block_type=item["blockType"],
                order_index=item["orderIndex"],
                section=item.get("section"),
                page_number=item.get("pageNumber"),
            )
            for item in raw["blocks"]
        ),
    )
