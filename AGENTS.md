# AGENTS.md

## 1. Purpose

This file defines persistent implementation rules for Codex and other coding agents working in this repository.

Repository: `prompt-generator-rag`

For detailed product requirements, architecture, milestones, data models, RAG behavior, UX, and acceptance criteria, use:

`MASTER_SPECIFICATION.md`

Do not load unrelated sections of the master specification unless needed for the current task.

Priority in case of conflict:

1. Current user task
2. `MASTER_SPECIFICATION.md` for product requirements
3. `AGENTS.md` for implementation behavior

---

## 2. Product

A bilingual Turkish/English platform that:

* converts vague user requests into structured `PromptSpec`,
* detects missing information,
* asks minimal clarification questions,
* compiles optimized prompts,
* optionally executes prompts,
* supports document-grounded prompting through RAG,
* exposes citations,
* evaluates retrieval quality.

The product must not become a thin LLM API wrapper.

---

## 3. Core Architecture

```text
apps/
  web/        # Next.js frontend
  api/        # FastAPI backend

packages/
  prompt-engine/
  rag/

evals/
database/
docs/
```

Keep these boundaries explicit:

```text
Web UI
   ↓
API
 ├── Prompt Engine
 ├── RAG Engine
 ├── Execution
 └── Persistence
```

Prompt Engine and RAG must remain independently testable.

---

## 4. Engineering Priorities

Prefer, in order:

1. correctness
2. security
3. clear architecture
4. measurability
5. maintainability
6. simplicity
7. performance

Prefer explicit code over framework magic.

Use deterministic logic when an LLM is unnecessary.

Avoid premature abstractions, microservices, and dependencies.

---

## 5. Prompt Engine Invariants

Canonical flow:

```text
User Input
   ↓
Intent Analysis
   ↓
PromptSpec
   ↓
Gap Analysis
   ↓
Optional Clarification
   ↓
Compilation
   ↓
Optional Execution
```

`PromptSpec` is:

* model-independent,
* the canonical representation of user intent,
* validated as structured data.

Do not generate final prompts directly from raw input when a `PromptSpec` exists.

Provider-specific behavior belongs in compiler/provider adapters.

Ask at most a few clarification questions and only when missing information materially affects quality.

---

## 6. Templates

Templates reduce cold-start friction.

They must:

* initialize `PromptSpec` hints,
* never bypass the Prompt Engine,
* remain editable,
* support TR/EN,
* allow explicit user input to override defaults.

Do not maintain a large library of hardcoded final prompts.

---

## 7. RAG Invariants

Target pipeline:

```text
Document
 ↓
Parse
 ↓
Normalize
 ↓
Structure-aware Chunk
 ↓
Metadata
 ↓
Embed
 ↓
Index

Query
 ↓
Dense Retrieval ─┐
                  ├→ RRF
Sparse Retrieval ┘
       ↓
    Reranker
       ↓
Context Builder
       ↓
Generation
       ↓
Citations
```

Final architecture must not be dense-only.

Core retrieval behavior should remain visible in repository code.

Do not hide the entire RAG pipeline behind LangChain/LlamaIndex abstractions.

Libraries may be used selectively.

---

## 8. Retrieval Rules

Initial production stack:

* PostgreSQL
* pgvector
* HNSW
* PostgreSQL lexical/full-text search
* Reciprocal Rank Fusion
* optional reranker

Retriever optimizes recall.

Reranker optimizes precision.

Do not directly add incompatible dense and sparse raw scores.

Use rank-based fusion such as RRF.

---

## 9. Chunking

Prefer structure-aware chunking:

```text
section
→ heading
→ paragraph
→ sentence
→ token boundary
```

Preserve useful metadata:

* document ID
* user/workspace ownership
* page
* section
* heading
* language
* chunk index

Do not default blindly to fixed-size splitting.

---

## 10. RAG Security

Uploaded documents are untrusted data.

Never treat instructions found inside documents as application/system instructions.

Retrieval must enforce ownership before returning results.

Relevant filters include:

* `user_id`
* `workspace_id`
* `document_id`

Cross-user document leakage is a critical failure.

Never fabricate citations, page numbers, or retrieved evidence.

---

## 11. Context & Grounding

Do not blindly send retrieved candidates to generation.

Context Builder should:

* deduplicate,
* reduce overlap,
* respect token budget,
* preserve citation metadata,
* prioritize relevance.

When evidence is insufficient, the system should say so rather than invent document-backed claims.

---

## 12. Evaluation

Retrieval changes should be measured whenever practical.

Core metrics:

* Recall@5
* Recall@10
* MRR
* nDCG@10
* Hit Rate

Support ablation comparisons:

```text
Sparse
Dense
Hybrid
Hybrid + Rewrite
Hybrid + Reranker
Full Pipeline
```

Do not make README performance claims without measured evidence.

Experimental notebooks may be used for RAG research; production implementations belong in repository modules.

---

## 13. API & Backend

Use versioned routes:

`/api/v1/...`

Route handlers should primarily:

* validate,
* authenticate,
* authorize,
* call services,
* serialize responses.

Do not put substantial business logic in route handlers.

External providers should be behind interfaces/adapters.

---

## 14. Database

All schema changes require migrations.

Prefer:

* foreign keys,
* indexes,
* unique constraints,
* ownership fields,
* timestamps.

Never rely on undocumented manual database state.

Do not create speculative tables before they are needed.

---

## 15. Errors

Maintain separation between:

```text
provider/infrastructure error
→ stable application error code
→ localized user message
```

Never expose:

* raw provider payloads,
* stack traces,
* secrets,
* internal configuration.

Never invent the cause of an error.

User-facing errors must be understandable in Turkish and English.

---

## 16. Rate Limits & Quotas

Rate limiting and usage quotas are separate concepts.

Rate limits protect against abuse/bursts.

Usage quotas protect cost/resource budgets.

Never hardcode plan limits inside business logic.

Usage must be calculated server-side.

---

## 17. Feedback

User feedback is a signal, not ground truth.

Do not automatically use feedback for:

* model training,
* fine-tuning,
* evaluation labels.

Preserve association with the relevant prompt/execution/version.

Use feedback initially for product analysis and manually reviewed dataset creation.

---

## 18. Privacy & Logging

Do not unnecessarily log:

* complete private documents,
* complete user prompts,
* secrets,
* credentials.

Prefer identifiers, timing, counts, model/version metadata, and safe structured events.

Deletion requirements must propagate to derived document/chunk data where applicable.

---

## 19. Dependencies

Before adding a dependency:

1. check whether existing code/dependencies already solve it,
2. consider maintenance cost,
3. prefer small focused libraries.

Do not introduce infrastructure merely because it is popular.

---

## 20. Testing

For changed behavior, add appropriate tests.

Priority:

```text
unit
→ integration
→ evaluation
```

Important test targets include:

* PromptSpec validation
* compilers
* gap logic
* chunking
* RRF
* metadata isolation
* context deduplication
* citation behavior

Run relevant checks after changes.

---

## 21. Agent Workflow

For each non-trivial task:

1. inspect only relevant files,
2. read relevant sections of `MASTER_SPECIFICATION.md`,
3. understand existing architecture,
4. make the smallest coherent change,
5. avoid unrelated refactors,
6. add/update tests,
7. run relevant checks,
8. fix failures caused by the change,
9. update docs only when behavior/architecture changed.

Do not implement future milestones unless requested.

---

## 22. Token-Efficient Behavior

Do not repeatedly load the entire `MASTER_SPECIFICATION.md`.

For each task, read only:

* this `AGENTS.md`,
* relevant source files,
* relevant specification sections.

Avoid:

* reproducing large specification sections,
* verbose generated comments,
* unnecessary placeholder files,
* rewriting unchanged files,
* repeated architecture explanations.

Use repository code and tests as executable context wherever possible.

---

## 23. Non-Goals

Unless explicitly requested, do not add:

* autonomous multi-agent systems,
* unnecessary microservices,
* Kubernetes,
* custom vector databases,
* custom foundation-model training,
* blockchain,
* native mobile apps,
* speculative enterprise infrastructure.

---

## 24. Definition of Done

A task is complete when:

* requested behavior works,
* architecture boundaries remain intact,
* security implications are addressed,
* relevant tests/checks pass,
* failures are handled,
* unnecessary changes were avoided,
* documentation is updated when required.

For retrieval changes, report measurable evaluation impact when applicable.
