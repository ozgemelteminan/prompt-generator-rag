# M6.3 RAG security evaluation

Deterministic fixture result: **10 / 10 passed**.

## By language

| Language | Passed |
| --- | ---: |
| en | 5 / 5 |
| tr | 5 / 5 |

## By attack category

| Category | Passed |
| --- | ---: |
| citation_fabrication | 2 / 2 |
| document_scope | 1 / 1 |
| error_sanitization | 1 / 1 |
| insufficient_evidence | 2 / 2 |
| prompt_injection | 2 / 2 |
| source_fabrication | 1 / 1 |
| workspace_isolation | 1 / 1 |

## Failures

None in this run.

## Limitations

- This deterministic suite validates application boundaries; it does not predict how every external model will react to adversarial text.
- Workspace/document scope uses the production service and repository with SQLite test storage; M6.1 supplies the separate pgvector smoke path.
- No live provider, model, or secret was used.
