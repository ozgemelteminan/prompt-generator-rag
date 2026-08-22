# Demo guide

## Portfolio summary

**Prompt Generator is a bilingual product that converts vague requests into a
canonical PromptSpec and a deterministic, reusable prompt, with optional
document-grounded answers and citations.**

Technical highlights:

- A provider-independent PromptSpec separates intent from HTTP, persistence, and
  model adapters; deterministic compilation adds no LLM call.
- The normal create path makes one semantic analysis call, asks at most four
  material clarification questions, and keeps execution explicit and separate.
- Document Q&A uses production structure-aware chunks (350/500/40), multilingual
  E5 embeddings, PostgreSQL + pgvector dense retrieval, bounded context, and
  deterministic citation validation.
- M4 real benchmarks selected structure-aware chunking and E5; E5 Dense achieved
  Recall@10 1.000, MRR 0.870, and nDCG@10 0.852 on the reviewed corpus.
- The current system is deliberately honest about limits: M6 answer, security,
  and operational results are deterministic harness evidence; live-provider and
  real pgvector smoke runs remain opt-in.

Core stack: Next.js, TypeScript, Tailwind CSS, FastAPI, Pydantic, SQLAlchemy,
Alembic, PostgreSQL/pgvector, and SentenceTransformers.

## Prerequisites and startup

Follow the concise local setup in the [README](../README.md#local-development).
For a demo that includes analysis, execution, document embedding, and grounded
generation, provide a valid selected-provider key (`GROQ_API_KEY` by default,
or `GEMINI_API_KEY` plus `GEMINI_MODEL`), a migrated PostgreSQL + pgvector
database, and an environment capable of loading the E5 embedding model. Use the
[deployment guide](DEPLOYMENT.md) for containerized startup and persistence.

Open the web application at `http://localhost:3000` when using the default local
ports. The following flow is intentionally linear: demonstrate the main Prompt
Generator first, then document intelligence.

## 1. Structured prompt generation

1. Open **Create** and leave the preset unselected to show free-form input.
2. Enter: `Write a concise project update email about the March release.`
3. Choose **English**, then select **Create prompt**.
4. If clarification questions appear, answer with concise specifics, for example:
   - Recipient: `External customers`
   - Tone: `Professional and confident`
5. Select **Continue**. Show the resulting optimized prompt, then use **Copy**.
6. Select **Run** only when a provider key is configured; show the execution
   output beside the compiled prompt.

What this demonstrates: one semantic intent-analysis call produces a canonical
PromptSpec; deterministic gap selection asks only material questions; the
compiler produces the final prompt without another model call; execution is a
separate, explicit provider request.

## 2. Document-grounded answer

Create a temporary local text file for the demo—do not add it to Git—with:

```text
Project Atlas will launch on 15 May. The customer migration begins on 1 May.
The release owner is the Platform team.
```

1. Open **Documents**, upload the file, and progress it until its badge reads
   **Ready**.
2. Open **Ask Documents** and select the ready document.
3. Ask: `When does Project Atlas launch and who owns the release?`
4. Select **Ask**. Read the grounded answer and use its inline `[1]`, `[2]`
   citations to move focus to the matching source cards.
5. Point out each source card’s filename, relevant excerpt, and any available
   page/section/heading metadata.

What this demonstrates: server-side upload validation, structured preparation,
workspace-scoped dense retrieval, a bounded ContextPackage, one grounded
generation attempt, provenance-preserving sources, and deterministic citation
validation. If evidence is insufficient, the product returns a friendly state
and makes no generation call.

## Reproducibility notes

- The demo uses real provider and embedding resources when configured; it may
  consume provider quota and time.
- Do not present the example document or its answer as a benchmark result.
- For pre-recorded portfolio material, capture only actual running UI states and
  redact keys, internal IDs, storage paths, and private document content.
- The screenshot inventory and capture order are in
  [`docs/screenshots/README.md`](screenshots/README.md).
