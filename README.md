# PromptForge

PromptForge is a bilingual Turkish/English product that turns an underspecified
request into a structured, reusable prompt. Its main product is a **structured
AI Prompt Generator**. Document-grounded question answering is an advanced,
separate subsystem that lets users ask questions against prepared documents with
source provenance.

The project is intentionally explicit about its decisions and evaluation
evidence: the Prompt Engine is provider-independent where possible, and RAG
experiments are kept separate from production implementation.

For a short product walkthrough, see [the demo guide](docs/DEMO.md). The
[architecture diagram](docs/ARCHITECTURE.md) and
[screenshot capture plan](docs/screenshots/README.md) support portfolio review.

## Project overview

Writing a useful prompt usually requires translating an informal request into a
clear objective, constraints, audience, format, and language. PromptForge makes
that work visible and repeatable instead of treating a model call as the product.
Users can start from free text or a small task preset, refine only material gaps,
copy the compiled prompt, and optionally run it. They can also prepare documents
and ask a single grounded question with inline citations.

## Product workflow

```text
User request
  → Intent Analysis
  → canonical PromptSpec
  → Gap Analysis
  → up to four clarification questions
  → deterministic Prompt Compiler
  → optimized prompt
  → optional execution
```

Presets are editable hints that initialize PromptSpec defaults; they never bypass
intent analysis or compilation. Explicit user input remains authoritative.

## Core Prompt Engine

`PromptSpec` is the validated, canonical, provider-independent representation of
intent. It captures task type/subtype, objective, Turkish or English response
language, optional context/audience/tone, requirements, constraints, output
preferences, source references, and missing-information items.

The normal generation path makes **one** semantic structured-analysis provider
call. `GapAnalyzer` then deterministically selects at most four material
questions. `GenericPromptCompiler` turns a complete PromptSpec into a stable
prompt with **zero LLM calls**. Optional execution is explicitly separate and
adds one provider call; it does not re-analyze or recompile the request.

This separation keeps provider behavior out of the core domain model, makes
PromptSpec and compilation independently testable, and avoids costly chains of
hidden model calls.

## Document and RAG subsystem

The document experience supports PDF, DOCX, TXT, and Markdown. It validates file
bytes and size server-side, parses and normalizes text, retains structure-aware
metadata, and exposes only product-facing preparation states.

```text
Upload → Validate → Parse → Normalize → Structure-aware Chunking
→ Passage Embedding → pgvector Index

Question → Query Embedding → Dense Retrieval → Context Builder
→ Grounded Generation → Citation Validation
```

The production path is:

```text
StructureAwareChunker(350/500/40)
→ intfloat/multilingual-e5-large-instruct
→ PostgreSQL + pgvector dense retrieval
→ Context Builder
→ grounded generation
→ citation validation
```

Passages use raw-text multilingual E5 embeddings; queries use E5's instructed
query format. Embeddings are normalized at dimension 1024. PostgreSQL + pgvector
uses cosine distance and HNSW indexing. The Context Builder deduplicates and
budgets evidence while retaining citation provenance. A response is generated
once only when evidence is sufficient; citations are checked deterministically
after generation without a second “citation repair” model call.

## RAG design decisions

- **Structure-aware chunks** preserve headings, sections, paragraphs, and useful
  metadata rather than blindly slicing a token stream.
- **Multilingual E5** was selected from the measured bilingual model comparison.
- **pgvector/HNSW** keeps vector search close to PostgreSQL ownership and document
  metadata, avoiding a separate vector-database service.
- **Dense-only production retrieval** is deliberately simpler than the research
  alternatives. Hybrid RRF improved ranking slightly but not recall and did not
  recover a Dense miss; it adds another retriever and operational surface.
- **The tested reranker is not enabled.** Its result applies only to the tested
  model, candidate depth, and corpus—not to all rerankers.

## Evaluation methodology and measured results

M4 uses committed real model/benchmark artifacts over a reviewed bilingual,
source-block-labeled retrieval corpus of 84 queries. The evaluation holds
documents, queries, labels, frozen chunks, cosine retrieval, top-k, and metrics
constant while varying the component under study. Metrics include Recall@5/10,
HitRate@5, MRR, nDCG@10, and required source-block coverage.

### Real M4 benchmark results

| Experiment | Selected / relevant result | Recall@10 | MRR | nDCG@10 |
| --- | --- | ---: | ---: | ---: |
| Chunking | Fixed chunking | 1.000 | 0.844 | 0.779 |
| Chunking | Structure-aware 350/500/40 | 1.000 | 0.899 | 0.818 |
| Embeddings | `intfloat/multilingual-e5-large-instruct` | 1.000 | 0.870 | 0.852 |
| Sparse baseline | BM25 | 0.958 | 0.845 | 0.825 |
| Hybrid research | Dense + BM25 + RRF | 1.000 | 0.877 | 0.857 |
| Reranker research | Dense + tested reranker | 0.982 | 0.874 | 0.845 |

The embedding comparison also measured GTE (MRR 0.802), BGE-M3 (0.828), and
Turkish E5 (0.817). E5 was the MRR leader. Hybrid RRF produced a small gain over
Dense (MRR +0.0074, nDCG@10 +0.0052) with unchanged Recall@10; Dense was retained
for production. The tested `BAAI/bge-reranker-v2-m3` configuration reduced
Recall@5 from 0.958 to 0.899 and nDCG@10 from 0.852 to 0.845, so it was excluded.

The full methodology, ablation, and limitations are recorded in
[the final evaluation report](evals/results/final/final_evaluation_v1.md) and
[the M4 recommendation](evals/results/final/m4_recommendation_v1.md).

### M6 validation: what it does and does not prove

M6 is primarily deterministic fixture/harness validation, not a second set of
live-model quality claims:

| Area | Evidence | Result |
| --- | --- | --- |
| Production parity | deterministic harness | 10/10 checks passed |
| Answer/citation | fixture harness | 12 reviewed cases; not live-provider quality |
| Security | deterministic fixture | 10/10 attack cases passed |
| Operations | local fixture | request-count and boundedness checks passed |

The following opt-in checks have **not** been executed: real PostgreSQL +
pgvector smoke, live-provider answer-quality evaluation, and real operational
latency/cost measurement. Fixture answer scores are not presented as production
answer quality, fixture timings are not latency targets, and deterministic
security checks do not establish universal live-model robustness.

## Security and grounding guarantees

- Workspace filtering is applied in retrieval before results are ranked or
  returned; explicit document scopes are validated.
- Retrieved documents are untrusted **data**. Instructions inside source text
  cannot override application grounding instructions.
- Only citation IDs included by the ContextPackage are valid. Invalid or
  out-of-range citations fail deterministically; no source or page metadata is
  invented or remapped.
- Insufficient evidence returns no answer and performs zero generation calls.
- Public responses exclude vectors, storage keys/paths, and provider internals.
- Provider and validation failures are mapped to stable application errors.

These are application invariants backed by tests and deterministic evaluation;
they are not a claim that any external model is immune to every adversarial input.

## Tech stack

| Layer | Technology |
| --- | --- |
| Web | Next.js App Router, TypeScript, Tailwind CSS |
| API | FastAPI, Pydantic, SQLAlchemy, Alembic |
| Prompt domain | Python package with provider-independent contracts |
| Database | PostgreSQL 16 + pgvector, cosine/HNSW vector search |
| Embeddings | `intfloat/multilingual-e5-large-instruct` via SentenceTransformers |
| Provider adapter | OpenAI Responses API behind application interfaces |
| Local deployment | Docker Compose |

## Repository structure

```text
apps/
  web/                 Next.js product UI
  api/                 FastAPI routes, services, repositories, migrations
packages/
  prompt-engine/       PromptSpec, analysis/gap/compiler contracts
evals/                 retrieval and RAG evaluation code, datasets, artifacts
database/              database notes
docs/                  operational documentation
```

## API overview

All public routes are versioned under `/api/v1`.

| Area | Representative endpoints |
| --- | --- |
| Health | `GET /health` |
| Prompt creation | `POST /prompts/generate`, `POST /prompts/execute` |
| Prompt history | `GET /prompts`, `GET /prompts/{id}`, favorite and feedback routes |
| Usage | `GET /usage` |
| Documents | upload, list, inspect, process, chunk, embed, delete |
| Retrieval / RAG | `POST /retrieval/search`, `POST /rag/ask` |

Routes validate and serialize; services own the use-case orchestration and
repositories own persistence and workspace-scoped retrieval.

## Local development

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+ with
pnpm, and Docker Compose.

```bash
cp .env.example .env
# For host-run API, set DATABASE_URL to your host-reachable PostgreSQL URL.
docker compose up -d postgres

cd apps/api
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
pnpm install
pnpm web:dev
```

Useful checks:

```bash
cd apps/api && uv run ruff format --check . && uv run ruff check . && uv run pytest
cd packages/prompt-engine && uv run --with pytest pytest
pnpm web:lint && pnpm web:typecheck && pnpm web:build
```

## Deployment

The repository includes minimal containers for web, API, PostgreSQL/pgvector,
and a migration job. Startup is PostgreSQL → migrations → API → web. Uploaded
documents are stored on a persistent mounted filesystem volume; losing that
volume makes document metadata unusable.

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for required environment variables,
CORS and production-debug rules, migration commands, persistent-storage
requirements, health checks, and the post-deploy smoke checklist.

## Trade-offs and limitations

- The reviewed retrieval corpus is small and not production traffic; no
  statistical significance analysis has been run.
- Production uses dense-only retrieval despite a small Hybrid RRF ranking gain,
  prioritizing a narrower operational surface until further live evidence exists.
- Only one reranker configuration was tested.
- Local filesystem document storage requires a persistent shared mount and is
  not yet an object-storage solution.
- Current rate limiting is process-local, so deployment should use one API
  replica until a shared limiter is introduced.
- Real pgvector smoke, live-provider answer evaluation, production latency, and
  token/cost reporting are still pending opt-in runs.
- The current workspace boundary is not a complete authentication system.

## Future work

- Run the pending real pgvector, provider answer-quality, latency, and cost
  evaluations against a larger held-out bilingual corpus.
- Add authenticated multi-user authorization and a shared rate-limit adapter.
- Revisit Hybrid RRF and alternative rerankers only with new measured evidence.
- Introduce durable object storage and backup/retention workflows for documents.
- Expand reviewed prompt and retrieval evaluation datasets before tuning behavior.
