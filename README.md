# PromptForge

PromptForge is a planned Turkish/English platform for turning a user’s request
into a well-structured prompt. This repository currently implements **M5.1 —
Production Embeddings + pgvector Indexing**. Query retrieval, RAG generation, and
authentication are not implemented.

## Architecture

```text
apps/web     Next.js App Router frontend
apps/api     FastAPI HTTP API and Alembic migrations
packages/prompt-engine  Provider-independent PromptSpec domain package
database     Database notes and local operational guidance
```

The web application reads its public API base URL from configuration. The API
uses versioned routes (`/api/v1`), stays thin at the HTTP boundary, and reserves
a service layer for future use-cases. PostgreSQL is run locally with pgvector;
the initial migration enables its `vector` extension but creates no business
tables.

## PromptSpec (M1.1)

`PromptSpec` is the canonical, provider-independent structured representation
of a user's intent. It is a Python/Pydantic model in
`packages/prompt-engine`; it has no HTTP, database, or LLM-provider dependency.

```json
{
  "version": "1.0",
  "task": {
    "type": "writing.email",
    "objective": "Write a concise project update email."
  },
  "language": "en",
  "requirements": ["Use a professional tone."],
  "constraints": [],
  "output": {"format": "email", "length": "short", "structure": []},
  "missingInformation": [
    {
      "field": "recipient",
      "importance": "helpful",
      "question": "Who will receive the email?"
    }
  ]
}
```

## Intent and gap analysis (M1.2)

`IntentAnalyzer` makes one request to a provider-neutral structured-analysis
backend and validates its result as `PromptSpec`. The package supplies only the
backend contract and concise analysis instructions; it has no production LLM
adapter or API endpoint.

`GapAnalyzer` then selects clarification questions without another model call:
required gaps first, then helpful gaps in their original order, at most four.
Optional and duplicate gaps are omitted. This keeps the normal production path
to one semantic analysis call plus deterministic selection.

Example flow:

```text
Raw input: "Write a project update email."
      ↓
PromptSpec: task=writing.email, language=en,
            missingInformation=[recipient (helpful)]
      ↓
ClarificationPlan: shouldClarify=true,
                   canGenerate=true,
                   questions=["Who will receive the email?"]
```

## Deterministic prompt compilation (M1.3)

`GenericPromptCompiler` converts a validated `PromptSpec` into a stable,
provider-independent executable prompt with **zero additional LLM calls**. It
uses concise English section labels, omits empty sections, and makes the
requested Turkish or English response language explicit. Requirements and
constraints remain separate; supplied source IDs are only references to use
when available, not claims of retrieval or citations.

Any unresolved `required` missing-information item raises an incomplete-spec
error instead of compiling a prompt. Helpful and optional gaps do not block it.

```text
PromptSpec: objective="Write a project update email",
            language=en, output.format=email
      ↓ GenericPromptCompiler
OBJECTIVE
Write a project update email.

OUTPUT
- Format: email

LANGUAGE
Write the final response in English.
```

## Prompt generation API (M1.4)

`POST /api/v1/prompts/generate` makes one OpenAI Responses API structured-output
request to produce `PromptSpec`. Gap selection and compilation are deterministic
and make no additional LLM calls. Set `OPENAI_API_KEY` and optionally
`OPENAI_MODEL` and `OPENAI_TIMEOUT_SECONDS` in `.env`; the default model is
`gpt-4.1-mini` and the timeout is 30 seconds.

Request:

```json
{"input":"Write a concise project update email.","language":"en"}
```

Ready response shape:

```json
{
  "state": "ready",
  "promptSpec": {"version": "1.0", "task": {"type": "writing.email", "objective": "..."}},
  "clarificationPlan": {"questions": [], "shouldClarify": false, "canGenerate": true},
  "compiledPrompt": "OBJECTIVE\n..."
}
```

If a required gap remains, the response instead has
`"state":"clarification_required"`, `compiledPrompt: null`, and the
clarification questions in `clarificationPlan`.

Run the API and make one manual request (this consumes API usage):

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/api/v1/prompts/generate \
  -H 'Content-Type: application/json' \
  -d '{"input":"Write a concise project update email.","language":"en"}'
```

## Create experience and presets (M2.1)

The web homepage is a simple guided create flow: select Turkish or English,
optionally choose a built-in task preset, describe the task, answer up to four
clarification questions when needed, then copy the generated prompt. It never
executes the prompt.

Presets are small provider-independent hints (for example `writing.email`),
not saved prompts. A selected preset is sent as `presetId` to the existing
generation endpoint and becomes a default hint for the single intent-analysis
call. Explicit user input always has priority.

```json
{
  "input": "Write an update for new customers.",
  "language": "en",
  "presetId": "write-email"
}
```

## Direct execution (M2.2)

When a generated prompt is ready, the create experience presents a separate,
explicit **Run** action. It sends the existing compiled prompt to
`POST /api/v1/prompts/execute`; it does not analyze, clarify, or compile again.
The result remains visible alongside the original compiled prompt and can be
copied or run again. Execution is plain text generation only: no tools, web
search, file search, code interpreter, document access, or persistence.

The API uses a provider-independent `ExecutionBackend` contract. The current
OpenAI Responses API adapter makes one text-generation request with `store=False`
and no retries. `OPENAI_EXECUTION_MODEL` optionally selects a different model for
execution; when unset it falls back to `OPENAI_MODEL`. Execution input is rejected
when blank or over `EXECUTION_MAX_INPUT_CHARACTERS` (20,000 by default), without
truncation.

```json
// POST /api/v1/prompts/execute
{"compiledPrompt":"OBJECTIVE\nWrite a concise project update email.\n\nLANGUAGE\nWrite the final response in English."}
```

```json
{"output":"Subject: Project update\n\nHello ..."}
```

To make an opt-in real-provider check after starting the API with a valid
`OPENAI_API_KEY`, first call `/api/v1/prompts/generate`, copy its ready
`compiledPrompt`, then execute it:

```bash
curl -X POST http://localhost:8000/api/v1/prompts/execute \
  -H 'Content-Type: application/json' \
  -d '{"compiledPrompt":"Write a short, friendly project update in English."}'
```

This consumes provider usage. The automated tests use fake execution backends
and never require an API key.

## History, favorites, and feedback (M2.3)

Ready prompt generations persist canonical PromptSpec JSON and their compiled
prompt. Each successful run creates a separate linked execution, preserving
reruns. Clarification-only and failed-provider responses are not normal history.
Favorites are a boolean on saved prompts. Feedback is append-only and may target
a prompt or execution; it never modifies PromptSpec, provider behavior, or
training data automatically.

The M2.3 migration creates `prompt_generations`, `prompt_executions`, and
`prompt_feedback`. Current ownership is a single unauthenticated local workspace:
records reserve a nullable `owner_id` boundary but no identity is fabricated.
Authentication must add authorization filters before multi-user use.

```text
GET  /api/v1/prompts?limit=20&offset=0&favoritesOnly=false
GET  /api/v1/prompts/{id}
PUT  /api/v1/prompts/{id}/favorite
POST /api/v1/prompts/{id}/feedback
```

## Limits, usage, and friendly errors (M2.4)

Generation and execution have separate configuration-driven controls:

- A thread-safe in-memory sliding-window rate limiter protects this single API
  process from bursts. It returns `rate_limit_exceeded` with HTTP 429 and a
  `Retry-After` value. A multi-process deployment must replace this adapter with
  shared rate-limit storage.
- Monthly quotas use PostgreSQL-backed reservations. A transaction-level advisory
  lock serializes each workspace/resource/month key, capacity is reserved before
  a provider call, and successful valid output atomically converts the reservation
  into an append-only `usage_events` row. This prevents ordinary concurrent quota
  overshoot without introducing Redis or a billing ledger.

Validation failures, invalid history IDs, rate-limit rejections, quota rejections,
provider failures, invalid structured analysis, and empty execution output do not
consume quota. After a valid provider result, usage is recorded before normal
history persistence. If downstream history persistence then fails, the usage stays
counted because provider resources were consumed. If authoritative usage accounting
fails, the request fails closed instead of returning unaccounted success. A process
crash during a provider request may leave a conservative reservation until the
monthly period changes; a durable expiring-reservation model is a future scaling
improvement.

`GET /api/v1/usage` returns provider-independent used, limit, remaining, and reset
time values for generation and execution. Stable machine error codes remain separate
from the centralized Turkish/English UI message mapping.

## Document ingestion and structure-aware chunking (M3.1–M3.3)

`POST /api/v1/documents` accepts multipart uploads and persists metadata only. It
supports PDF, DOCX, TXT, and Markdown after server-side byte validation; browser
MIME values and filename extensions alone are never trusted. Empty files, oversized
files, unsafe filenames, and unsupported bytes return stable document error codes.

Each `documents` row contains a workspace boundary, original filename, detected media
type, size, SHA-256 checksum, nullable language, status, timestamps, and an internal
storage key. It intentionally does **not** contain parsed text, chunks, or embeddings.
The M3.1 migration creates this table with a unique `workspace_id + checksum` constraint.

The local filesystem storage adapter generates internal keys and never exposes them
through the API. Identical content uploaded to the same workspace returns the existing
document with `deduplicated: true`, avoiding duplicate storage and later processing.
The same content in another workspace is separate. This remains a local unauthenticated
workspace boundary, not authentication.

M3.2 adds an explicit synchronous processing step:

```text
stored original → parser → normalized ordered blocks → persisted blocks
```

The parser adapters are local-only and receive bytes through the existing storage
boundary. They use `pypdf` for PDF text extraction and `python-docx` for DOCX parsing.
PDF parsing extracts text per page without OCR; DOCX retains paragraphs and reliable
heading styles; UTF-8 TXT retains paragraphs; and Markdown retains headings, list items,
and fenced code as untrusted document data. Deterministic normalization cleans line
endings, accidental spacing, and control characters without rewriting or summarizing
content. A conservative local heuristic records `tr`, `en`, or null.

Parsed content is stored in a separate ordered `document_blocks` relation with optional
page, heading level, and section context. Processing changes status from `uploaded` to
`processing` to `parsed`; failures preserve the original upload, leave no partial
replacement blocks, and set status to `failed`.

M3.3 converts parsed blocks into `document_chunks` through a local, deterministic
structure-aware chunker:

```text
parsed blocks → section/heading → paragraph → sentence → token fallback → chunks
```

The default budgets are `CHUNK_TARGET_TOKENS=350`, `CHUNK_MAX_TOKENS=500`, and
`CHUNK_OVERLAP_TOKENS=40`. Token counts use an isolated Unicode-aware regex tokenizer:
they are stable local sizing estimates, not an embedding-provider contract. Overlap is
conservative, consists only of complete trailing structural units, and never crosses a
heading/section boundary or exceeds the maximum. Chunks retain workspace/document IDs,
stable index, language, section/heading, source-block range, and genuine PDF page range.
Re-chunking transactionally replaces the current set and returns count/min/max/average
token statistics. The lifecycle is `parsed → chunking → chunked`; **chunked does not
mean embedded, indexed, or RAG-ready**.

```text
POST   /api/v1/documents
GET    /api/v1/documents
GET    /api/v1/documents/{id}
POST   /api/v1/documents/{id}/process
POST   /api/v1/documents/{id}/chunk
DELETE /api/v1/documents/{id}
```

Deletion removes the stored original before removing its database row; a storage failure
leaves the metadata intact rather than silently creating an inconsistent record.

## Production embeddings and pgvector indexing (M5.1)

M5.1 adds the first production-ready vector step, without adding search or RAG:

```text
chunked document → raw-passage E5 embeddings → pgvector rows → HNSW cosine index → embedded
```

`POST /api/v1/documents/{id}/embed` is workspace-scoped and accepts only a chunked (or
already embedded) document. It loads chunks in stable order, embeds raw chunk text in
configuration-driven batches with `intfloat/multilingual-e5-large-instruct`, normalizes
the vectors, and transactionally replaces the document's current vector rows. It returns
only document metadata, counts, status, and model ID; vectors are never exposed over HTTP.

The `document_embeddings` table preserves chunk/document/workspace references, model ID,
dimension, and timestamp. It stores native `vector(1024)` values and owns a cosine HNSW
index (`vector_cosine_ops`). Re-embedding replaces rows rather than creating duplicates;
if model loading, embedding, dimensions, or persistence fail, the document is never marked
`embedded`. This is dense-only indexing; M5.2 must add any query embedding and retrieval
behavior explicitly.

```text
POST /api/v1/documents/{id}/embed
```

## Production dense retrieval (M5.2)

`POST /api/v1/retrieval/search` searches only embeddings belonging to the current local
workspace and current configured embedding model. It embeds the query exactly once using:

```text
Instruct: Given a web search query, retrieve relevant passages that answer the query
Query: <query>
```

Passages remain raw chunk text. PostgreSQL applies workspace, model, dimension, and optional
document filters in the vector query before ordering by `embedding <=> query_vector` and
limiting results. The default top-k is `5`, maximum is `20`, configured through
`RETRIEVAL_DEFAULT_LIMIT` and `RETRIEVAL_MAX_LIMIT`. HNSW settings use transaction-local
`hnsw.ef_search` and strict-order iterative scan configuration. Returned chunks contain source
metadata and distance/similarity only—never vectors, citations, context assembly, or answers.
An explicitly selected document must be embedded; an embedded document with stale/incompatible
model vectors produces no results rather than mixing vector spaces.

## Context package and citation provenance (M5.3)

M5.3 converts the already ranked dense-retrieval chunks into a deterministic, provider-neutral
context package for a future grounded-generation layer. It never retrieves, embeds, or calls a
model again. In retrieval order, it removes duplicate chunk IDs, normalized-identical text, and
same-document source-block ranges with at least 80% overlap of the smaller range. Distinct nearby
evidence remains available.

`RAG_CONTEXT_MAX_TOKENS` (default `2000`) is enforced with a local Unicode-aware token counter;
sources that do not wholly fit are omitted rather than truncated or summarized. Included sources
receive sequential `[1]`, `[2]`, … labels and retain document/chunk IDs, filename, page range when
present, section, heading, similarity, and source-block range. Context is explicitly marked as
**untrusted data**: document text is evidence, never application instructions. Empty, deduplicated,
or over-budget inputs yield an `insufficient_evidence` package for M5.4 to handle safely.

## Grounded document answers (M5.4)

`POST /api/v1/rag/ask` connects the existing dense retrieval and context builder to one
provider-neutral generation call. A request retrieves once, builds one context package, and makes
no generation call when evidence is insufficient. The generation instruction requires answers only
from supplied sources, treats document text as untrusted data, and permits only the context
package’s sequential citation IDs. Returned source provenance includes citation/document/chunk IDs,
filename, page range, section, heading, excerpt, and similarity; vectors and storage details remain
private. Invalid generated citations fail safely rather than being repaired or fabricated.

Usage accounting is intentionally deferred: the current guard has only prompt-generation and
prompt-execution actions, so M5.4 does not misclassify grounded-generation cost under either quota.

## Chunking evaluation (M4.1)

M4.1 is an offline experiment, not a production retrieval feature. It compares an
evaluation-only fixed-size baseline, an evaluation-only recursive baseline, and the
real production `StructureAwareChunker` imported from
`apps/api/app/document_processing/chunking.py`. The production algorithm is not copied
into evaluation code or the notebook.

The static `chunking-eval-v1` dataset has six block-structured documents (three Turkish,
three English) and 42 reviewable queries across factual, paraphrase,
heading-dependent, cross-paragraph, terminology-mismatch, and morphology-heavy cases.
Ground truth refers to source block IDs rather than generated chunk IDs. A chunk is
relevant exactly when its source-block IDs intersect the query's relevant block IDs.

All three strategies use one fixed embedding model—`Alibaba-NLP/gte-multilingual-base`—
with identical query encoding, cosine retrieval, depth, and metrics. This isolates
chunking strategy. The shared evaluation modules calculate Recall@5, Recall@10,
HitRate@5, MRR, nDCG@10, chunk-size statistics, overlap ratio, and model-tokenizer
truncation rate. Results are grouped by language and query category.

Run the official experiment in [the Colab notebook](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/01_chunking_experiments.ipynb): set the clone URL and ref in its first cell, then use **Run all** in a fresh runtime. Before any ML imports, setup pins `transformers==4.57.6` and `sentence-transformers==5.6.0`, prints/asserts the active versions, and records Torch, Transformers, Sentence Transformers, and CUDA-device details in official result metadata. It then updates an existing clone before imports, explicitly adds both the repository root and `apps/api` to Python imports, and fails early if stale evaluation modules are already loaded. It initializes `Alibaba-NLP/gte-multilingual-base` through the evaluation adapter with its required explicit `trust_remote_code=True` opt-in, then executes the three strategies, displays comparison/breakdown tables, and writes official JSON/CSV artifacts to `evals/results/chunking/`.

For local evaluation tests only (the debug hash embedder is intentionally not official):

```bash
PYTHONPATH=apps/api:. uv run pytest evals/tests
```

The committed result files are deliberately marked `requires_real_model_run`; no fake
hash-embedder numbers are presented as benchmark results.

## Embedding benchmark (M4.2)

M4.2 evaluates four embedding models over a single frozen chunk corpus generated once
by the production `StructureAwareChunker` with target/max/overlap tokens of 350/500/40.
Documents, retrieval queries, source-block relevance labels, cosine ranking, and metrics
are held fixed. The only variable is embedding model: GTE multilingual base, BGE-M3,
multilingual E5 large instruct, and Turkish E5 large.

The static `retrieval-eval-v1` dataset has 84 balanced Turkish/English queries and adds
hard paraphrase, near-negative, same-topic competitor, and multi-section categories.
It retains block-based ground truth. M4.2 adds RequiredBlockCoverage@5/@10: the fraction
of required source blocks represented by top-k chunks. It records quality breakdowns plus
embedding dimension, load/encode timing, throughput, truncation rate, and peak CUDA memory.

The evaluation registry uses each model's retrieval formatting protocol:

| Model | Query formatting | Passage formatting | Scope |
| --- | --- | --- | --- |
| `Alibaba-NLP/gte-multilingual-base` | Raw query | Raw passage | Bilingual; remote code explicitly enabled |
| `BAAI/bge-m3` | Raw query | Raw passage | Bilingual |
| `intfloat/multilingual-e5-large-instruct` | `Instruct: Given a web search query, retrieve relevant passages that answer the query` then `Query: <query>` | Raw passage | Bilingual |
| `ytu-ce-cosmos/turkish-e5-large` | `Instruct: Given a Turkish search query, retrieve relevant passages written in Turkish that best answer the query` then `Query: <query>` | Raw passage | Turkish-specialized; English results are diagnostic only |

The M4.2 notebook reports Turkish metrics separately. Turkish E5 is not considered a
general bilingual production winner from its Turkish-language results.

Run [02_embedding_benchmark.ipynb](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/02_embedding_benchmark.ipynb) in a fresh Colab runtime after setting its repository URL/ref. It uses the same pinned compatible runtime as M4.1, loads one model at a time, writes results incrementally to `evals/results/embeddings/`, and releases CUDA memory between models. No official model results are committed.

## Sparse vs dense retrieval benchmark (M4.3)

M4.3 compares two separate baselines over the exact frozen M4.2 chunks and
`retrieval-eval-v1` labels: dense `intfloat/multilingual-e5-large-instruct` using the
existing model adapter, and an evaluation-only in-memory BM25 lexical retriever. BM25
uses deterministic Unicode case-folded word tokens (including Turkish characters), with
`k1=1.5` and `b=0.75`; it has no stemming or language-specific analyzer.

Both paths reuse the centralized retrieval metrics and produce overall, Turkish/English,
and category breakdowns. They are deliberately not fused; the notebook identifies their
separate category strengths to inform a future hybrid experiment. Run
[03_sparse_dense_baselines.ipynb](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/03_sparse_dense_baselines.ipynb)
in a fresh Colab runtime after setting its repository URL/ref. It writes only real-run
artifacts to `evals/results/retrieval/`; committed files are placeholders.

## Hybrid retrieval benchmark (M4.4)

M4.4 compares the same frozen E5 dense and BM25 sparse rankings with a third,
evaluation-only Reciprocal Rank Fusion baseline. Fusion uses rank positions only:
`1 / (k + rank)`, with `k=60` and the top 20 candidates from each retriever. It does
not rerank or add raw dense and sparse scores. The notebook reports overall,
Turkish/English, category, delta, and per-query complementary-signal diagnostics.

Run [04_hybrid_rrf.ipynb](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/04_hybrid_rrf.ipynb)
in a fresh Colab runtime after setting its repository URL/ref. It writes only real-run
artifacts to `evals/results/hybrid/`; committed files are placeholders.

## Multilingual reranker benchmark (M4.5)

M4.5 compares dense and hybrid RRF top-20 pools before and after the evaluation-only
`BAAI/bge-reranker-v2-m3` cross-encoder. After reranking, only cross-encoder relevance
scores determine the final order; prior dense, BM25, and RRF scores are not mixed in.
It records quality, language/category breakdowns, pair-scoring efficiency, and
per-query rescue/harm diagnostics.

Run [05_reranker_benchmark.ipynb](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/05_reranker_benchmark.ipynb)
in a fresh Colab runtime after setting its repository URL/ref. It writes only real-run
artifacts to `evals/results/reranking/`; committed files are placeholders.

## Full M4 ablation and recommendation (M4.6)

M4.6 consolidates the completed official M4 artifacts without rerunning models. The
measured M4 default carried forward is StructureAwareChunker (350/500/40) with
`intfloat/multilingual-e5-large-instruct` dense retrieval. Hybrid RRF is retained for
future validation, not selected as the default: its ranking gain was small, recall was
unchanged, English MRR declined, and it recovered no Dense miss. The tested
`BAAI/bge-reranker-v2-m3` is excluded because it reduced key recall/ranking metrics in
the evaluated configuration.

See [m4_recommendation_v1.md](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/evals/results/final/m4_recommendation_v1.md)
or run [06_full_ablation.ipynb](/Users/ozge/Documents/ChatGPT/prompt-generator-rag/notebooks/06_full_ablation.ipynb)
to regenerate the consolidated CSV/JSON/Markdown from committed results only.

## Prerequisites

- Node.js 20+ and [pnpm](https://pnpm.io/)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Docker Desktop (or Docker Engine with Compose)

## Setup

From the repository root:

```bash
cp .env.example .env
pnpm install
cd apps/api && uv sync --all-groups
```

The provided `.env.example` contains local-development values only. Change
`POSTGRES_PASSWORD` before using anything beyond a local machine. Required
variables are:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` for Compose
- `DATABASE_URL` and `CORS_ORIGINS` for the API
- `OPENAI_API_KEY` for live prompt generation and execution; `OPENAI_EXECUTION_MODEL`
  optionally overrides the execution model, and `EXECUTION_MAX_INPUT_CHARACTERS`
  limits accepted execution input
- `LOCAL_WORKSPACE_ID` identifies the current local workspace for guardrails; it
  is not authentication
- `RATE_LIMIT_GENERATE_REQUESTS`, `RATE_LIMIT_EXECUTE_REQUESTS`, and
  `RATE_LIMIT_WINDOW_SECONDS` configure single-process burst limits
- `GENERATION_QUOTA_PER_MONTH` and `EXECUTION_QUOTA_PER_MONTH` configure monthly
  workspace usage allowances
- `DOCUMENT_MAX_UPLOAD_BYTES` limits server-side upload reads (10 MiB by default)
- `DOCUMENT_STORAGE_PATH` selects a repository-relative local storage root; it is an
  internal implementation setting and is never sent to the frontend
- `CHUNK_TARGET_TOKENS`, `CHUNK_MAX_TOKENS`, and `CHUNK_OVERLAP_TOKENS` control local
  structure-aware chunk sizing; maximum must be at least target and overlap smaller than
  maximum
- `NEXT_PUBLIC_API_BASE_URL` for the web app

## Start the database and migrate it

From the repository root:

```bash
docker compose up -d postgres
cd apps/api && uv run alembic upgrade head
```

Check its status with `docker compose ps`. Stop it with `docker compose down`.
Add `-v` only when you deliberately want to remove local database data.

## Run locally

In one terminal, start the API:

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

The health endpoint is available at <http://localhost:8000/api/v1/health> and
returns:

```json
{"status":"ok"}
```

In another terminal, start the frontend:

```bash
pnpm --dir apps/web dev
```

Open <http://localhost:3000>.

## Quality commands

Backend, from `apps/api`:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Prompt Engine package, from `packages/prompt-engine`:

```bash
uv run --with pytest --with ruff pytest
uv run --with ruff ruff format --check .
uv run --with ruff ruff check .
```

Frontend, from the repository root:

```bash
pnpm web:lint
pnpm web:typecheck
pnpm web:build
```
