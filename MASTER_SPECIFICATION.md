# MASTER_SPECIFICATION.md

## 1. Product

Working name: **PromptForge**

Category:

**AI Prompt Generation, Optimization and Document-Grounded Execution Platform**

Primary languages:

```text
Turkish
English
```

This document is the product and architecture source of truth.

---

# 2. Product Vision

Users should not need to understand prompt engineering.

The user explains what they want in normal language.

The system determines:

```text
intent
context
missing information
requirements
constraints
output format
language
relevant document context
```

and produces an optimized prompt.

Optionally, the system executes that prompt and returns the final result.

Core principle:

> The user describes the task. The system handles prompt engineering.

---

# 3. Target Users

### Primary

Non-technical users who:

- use AI tools,
- struggle to write effective prompts,
- do not know prompt-engineering terminology.

### Secondary

Power users who:

- want reusable prompts,
- want structured control,
- compare prompt variants,
- use uploaded documents,
- want model-specific prompting.

### Developer / portfolio objective

The repository must demonstrate:

- software architecture,
- structured LLM orchestration,
- information retrieval,
- hybrid search,
- reranking,
- RAG evaluation,
- security,
- real product design.

---

# 4. Core User Flow

```text
User enters request
        ↓
Select TR / EN
        ↓
Intent Analyzer
        ↓
PromptSpec
        ↓
Gap Analyzer
        ↓
Missing critical information?
   ┌────────┴────────┐
  yes               no
   ↓                 │
Ask ≤4 questions     │
   └────────┬────────┘
            ↓
     Compile Prompt
            ↓
       Prompt Preview
       ┌────┴─────┐
       ↓          ↓
     Copy       Execute
                  ↓
              AI Result
```

If documents are attached:

```text
User Request
     +
Selected Documents
          ↓
Query Processing
          ↓
RAG Retrieval
          ↓
PromptSpec.context
          ↓
Prompt Compilation
```

---

# 5. Product Modes

## 5.1 Simple

User provides:

```text
task
language
```

System handles everything else.

Ideal for non-technical users.

---

## 5.2 Guided

System may ask contextual questions.

Typical fields:

```text
goal
audience
tone
context
constraints
desired output
```

Do not expose prompt-engineering terminology unnecessarily.

---

## 5.3 Advanced

User may inspect/edit:

```text
Objective
Context
Audience
Requirements
Constraints
Tone
Output
Sources
```

Advanced mode should manipulate PromptSpec rather than raw internal implementation state.

---

# 6. Primary Features

## MVP

- account/authentication
- Turkish and English
- free-text task input
- intent detection
- PromptSpec generation
- missing-information detection
- dynamic clarification questions
- prompt compilation
- prompt preview
- prompt editing
- copy prompt
- execute prompt
- prompt history
- favorite prompts
- document upload
- RAG retrieval
- source citations
- retrieval evaluation framework

---

# 7. Later Features

Not required for initial MVP:

```text
model-specific compilers
prompt A/B testing
automatic prompt optimization
prompt reconstruction
team workspaces
shared prompt templates
public prompt marketplace
advanced analytics
multiple execution providers
```

Architect for future support without implementing prematurely.

---

# 8. PromptSpec

`PromptSpec` is the canonical structured representation of user intent.

Suggested V1:

```ts
interface PromptSpec {
  version: "1.0";

  task: {
    type: TaskType;
    objective: string;
  };

  language: "tr" | "en";

  context?: string;
  audience?: string;
  tone?: string;

  requirements: string[];
  constraints: string[];

  output: {
    format?: string;
    length?: "short" | "medium" | "long";
    structure?: string[];
  };

  sources?: {
    documentIds: string[];
  };

  missingInformation: {
    field: string;
    importance: "required" | "helpful" | "optional";
    question: string;
  }[];
}
```

---

# 9. Task Taxonomy

Initial task families:

```text
writing
research
analysis
coding
learning
summarization
brainstorming
planning
translation
data
image_generation
general
```

Optional subtypes:

```text
writing.email
writing.social
writing.report

coding.debug
coding.generate
coding.review

research.compare
research.explain
research.deep

data.analyze
data.transform
```

Do not create excessive taxonomy before data demonstrates the need.

---

# 10. Intent Analyzer

Input:

```text
raw user request
language
optional conversation context
optional selected documents
```

Output:

```text
PromptSpec draft
```

Responsibilities:

- determine task type,
- infer explicit requirements,
- identify constraints,
- identify expected output,
- identify audience/tone when present,
- detect missing information.

It must not invent important facts.

---

# 11. Gap Analyzer

Purpose:

Determine whether missing information is worth asking the user.

Rules:

```text
required → normally ask
helpful  → ask only if high impact
optional → continue
```

Maximum recommended clarification count:

```text
4
```

Questions should be:

- short,
- understandable,
- non-technical,
- non-redundant.

---

# 12. Prompt Compiler

Input:

```text
PromptSpec
```

Output:

```text
final executable prompt
```

A prompt may contain only relevant sections.

Possible structure:

```text
ROLE
OBJECTIVE
CONTEXT
REQUIREMENTS
AUDIENCE
TONE
CONSTRAINTS
SOURCES
OUTPUT
LANGUAGE
```

Do not add empty sections.

Do not use exaggerated personas without a functional reason.

---

# 13. Prompt Compilation Principle

Prompt quality should optimize:

```text
clarity
specificity
necessary context
constraint precision
output definition
grounding
brevity
```

Not prompt length.

---

# 14. Direct Execution

Users may execute generated prompts without leaving the product.

Flow:

```text
PromptSpec
 ↓
Compiler
 ↓
Execution Provider
 ↓
Response
```

Store linkage between:

```text
original request
PromptSpec
compiled prompt
execution
response
```

where privacy settings allow it.

---

# 15. Prompt History

Each saved generation may include:

```text
id
user_id
original_request
prompt_spec
compiled_prompt
language
task_type
created_at
updated_at
is_favorite
```

Users should be able to:

- reopen,
- duplicate,
- edit,
- rerun,
- favorite,
- delete.

---

# 16. Document RAG

The RAG subsystem is a major engineering component.

Objectives:

1. support user-provided documents,
2. retrieve relevant evidence,
3. improve context quality,
4. preserve citations,
5. minimize hallucination,
6. provide measurable retrieval performance.

---

# 17. RAG Pipeline

```text
INGESTION

Upload
 ↓
Validate
 ↓
Extract
 ↓
Normalize
 ↓
Language Detection
 ↓
Structure Detection
 ↓
Chunk
 ↓
Metadata
 ↓
Embed
 ↓
Index


RETRIEVAL

Question
 ↓
Query Analysis
 ↓
       ┌─────────────────┐
       ↓                 ↓
Dense Retrieval   Sparse Retrieval
       └────────┬────────┘
                ↓
            RRF Fusion
                ↓
             Reranker
                ↓
          Context Builder
                ↓
             Generator
                ↓
         Answer + Sources
```

---

# 18. Supported Documents

Initial:

```text
PDF
DOCX
TXT
Markdown
```

Potential later support:

```text
HTML
CSV
PPTX
XLSX
URLs
```

---

# 19. Document Entity

```ts
interface Document {
  id: string;

  userId: string;
  workspaceId?: string;

  filename: string;
  mimeType: string;

  language: "tr" | "en" | "mixed";

  checksum: string;

  storageKey: string;

  status:
    | "uploaded"
    | "processing"
    | "indexed"
    | "failed";

  createdAt: Date;
  updatedAt: Date;
}
```

---

# 20. Chunk Entity

```ts
interface DocumentChunk {
  id: string;

  documentId: string;
  userId: string;
  workspaceId?: string;

  chunkIndex: number;

  content: string;

  heading?: string;
  section?: string;
  pageNumber?: number;

  language: "tr" | "en" | "mixed";

  tokenCount: number;

  embedding: number[];
}
```

---

# 21. Chunking

Default strategy:

**structure-aware recursive chunking**

Priority:

```text
section
→ heading
→ paragraph
→ sentence
→ token boundary
```

Goals:

- preserve semantic units,
- avoid tiny fragments,
- avoid excessive context,
- preserve metadata,
- minimize duplicated overlap.

Chunking configuration should be configurable.

---

# 22. Embeddings

Embedding service must be provider-independent.

```ts
interface EmbeddingProvider {
  embedText(text: string): Promise<number[]>;
  embedBatch(texts: string[]): Promise<number[][]>;
}
```

Store embedding-model identity/version with indexed data where needed to support future migrations.

---

# 23. Vector Storage

Initial:

```text
PostgreSQL
+
pgvector
+
HNSW
```

Reasons:

- relational metadata and vectors together,
- simple operational architecture,
- metadata filtering,
- sufficient MVP scale,
- SQL visibility.

Do not introduce a separate vector database without measured need.

---

# 24. Dense Retrieval

Dense retrieval provides semantic matching.

Input:

```text
query embedding
filters
top_k
```

Output:

```text
ranked candidate chunks
```

Use ANN for scalable lookup.

---

# 25. Sparse Retrieval

Sparse search improves:

- exact terminology,
- IDs,
- product codes,
- article numbers,
- course codes,
- names,
- uncommon keywords.

Initial implementation:

```text
PostgreSQL Full-Text Search
```

---

# 26. Hybrid Retrieval

Run both:

```text
dense retrieval
sparse retrieval
```

then fuse results.

Initial fusion:

**Reciprocal Rank Fusion**

```text
score(d) =
Σ 1 / (k + rank_i(d))
```

Avoid arbitrary weighted addition of incomparable retrieval scores.

---

# 27. Reranking

Pipeline:

```text
Hybrid Retrieval
      ↓
20–50 candidates
      ↓
Reranker
      ↓
5–10 chunks
```

Reranker receives:

```text
query
candidate chunk
```

and returns relevance score.

Keep reranking optional for evaluation.

---

# 28. Query Analyzer

Potential outputs:

```ts
interface RetrievalQuery {
  original: string;

  normalized?: string;

  language: "tr" | "en";

  rewrittenQueries?: string[];

  filters?: {
    documentIds?: string[];
    workspaceId?: string;
  };
}
```

Query rewriting should be conditional.

---

# 29. Multi-Query Retrieval

For multi-part user questions, decompose retrieval intent.

Example:

```text
"What happens if I resign and when must I return the laptop?"
```

May become:

```text
employee resignation consequences
employee notice period
company equipment return deadline
```

Results are merged before reranking.

---

# 30. Retrieval Filters

Retrieval must enforce:

```text
user ownership
workspace scope
selected documents
```

Never retrieve content from another user's documents.

---

# 31. Context Builder

Input:

```text
reranked chunks
token budget
```

Responsibilities:

- deduplicate,
- reduce overlap,
- maintain relevance ordering,
- preserve citations,
- group adjacent passages when useful,
- enforce token limit.

Output:

```ts
interface RetrievedContext {
  chunks: RetrievedChunk[];
  tokenCount: number;
}
```

---

# 32. RAG + Prompt Engine Integration

Retrieved content must not bypass PromptSpec.

Preferred flow:

```text
User Intent
   ↓
PromptSpec
   +
Retrieved Context
   ↓
Context Attachment
   ↓
Prompt Compiler
```

PromptSpec may store references rather than entire document bodies.

---

# 33. Grounding Policy

When RAG mode is enabled:

The model should:

- use provided evidence,
- distinguish evidence from inference,
- avoid unsupported document claims,
- admit when information is unavailable,
- cite supporting passages.

Retrieved document text must be treated as **data**, not trusted system instructions.

---

# 34. Prompt Injection Protection

Uploaded documents are untrusted.

Ignore embedded instructions attempting to:

- override system rules,
- expose secrets,
- change application behavior,
- request hidden prompts,
- retrieve unrelated documents.

Document content is evidence only.

---

# 35. Citation Model

Suggested structure:

```ts
interface Citation {
  id: string;
  chunkId: string;
  documentId: string;

  filename: string;

  pageNumber?: number;
  section?: string;

  excerpt?: string;
}
```

UI output example:

```text
The notice period is 30 days. [1]

[1] employment-contract.pdf
Page 12 — Termination
```

---

# 36. Retrieval Evaluation

Evaluation is part of the product architecture.

Dataset format:

```json
{
  "id": "q001",
  "query": "...",
  "relevantChunkIds": ["..."],
  "expectedAnswer": "..."
}
```

Core metrics:

```text
Recall@5
Recall@10
MRR
nDCG@10
Hit Rate
```

---

# 37. Generation Evaluation

Potential dimensions:

```text
Correctness
Faithfulness
Context relevance
Citation correctness
Instruction following
Completeness
```

Prefer repeatable scoring over arbitrary “prompt quality 92/100” claims.

---

# 38. Ablation Framework

Required comparisons:

| Pipeline | Purpose |
|---|---|
| Sparse | lexical baseline |
| Dense | semantic baseline |
| Hybrid | fusion improvement |
| Hybrid + Rewrite | query improvement |
| Hybrid + Rerank | precision improvement |
| Full Pipeline | final system |

Results belong in:

```text
evals/reports/
```

---

# 39. Prompt Quality Feedback

User-facing quality should explain missing components instead of giving meaningless single scores.

Example:

```text
Prompt Readiness: HIGH

Objective       ✓ Clear
Context         ✓ Sufficient
Audience        ! Missing
Constraints     ✓ Clear
Output Format   ✓ Defined
```

Optional dimension scores:

```text
Clarity
Context
Constraints
Output Definition
```

---

# 40. A/B Prompt Testing — V2

Generate:

```text
Variant A
balanced

Variant B
more structured
```

Execute with equal model parameters.

Evaluate against:

```text
instruction following
relevance
completeness
grounding
format adherence
```

Never claim one is universally superior based on one sample.

---

# 41. Prompt Reconstruction — V2

Input:

```text
existing AI output
```

System estimates:

```text
likely objective
audience
tone
constraints
structure
```

Then generates:

> A prompt likely to produce a similar result.

Do not claim recovery of the original hidden prompt.

---

# 42. Frontend

Recommended:

```text
Next.js
TypeScript
Tailwind
```

Main pages:

```text
/
 /create
 /history
 /documents
 /prompts/:id
 /settings
```

---

# 43. Main Create Screen

Desktop concept:

```text
┌──────────────────────────────────────────────┐
│               PromptForge                    │
├───────────────────┬──────────────────────────┤
│                   │                          │
│  User Request     │  Generated Prompt        │
│                   │                          │
│  Clarifications   │  Live Preview            │
│                   │                          │
│  Documents        │                          │
│                   │                          │
├───────────────────┴──────────────────────────┤
│ Copy        Improve        Run Prompt         │
└──────────────────────────────────────────────┘
```

Mobile should collapse to a single-column flow.

---

# 44. Language UX

Language is user-controlled.

Options:

```text
Türkçe
English
```

Prompt execution output defaults to selected language unless overridden by the task.

Do not infer that Turkish UI always means Turkish generated output.

---

# 45. Backend

Recommended:

```text
FastAPI
Python
```

Reasons:

- retrieval ecosystem,
- NLP tooling,
- evaluation tooling,
- async support.

Frontend and API remain separate applications.

---

# 46. API Surface

Suggested V1:

```text
POST /api/v1/prompts/analyze
POST /api/v1/prompts/clarify
POST /api/v1/prompts/compile
POST /api/v1/prompts/execute

GET  /api/v1/prompts
GET  /api/v1/prompts/{id}
PUT  /api/v1/prompts/{id}
DELETE /api/v1/prompts/{id}

POST /api/v1/documents
GET  /api/v1/documents
GET  /api/v1/documents/{id}
DELETE /api/v1/documents/{id}

POST /api/v1/retrieval/search
```

Internal service interfaces may differ from public API design.

---

# 47. Background Processing

Document ingestion should not block normal requests.

Potential architecture:

```text
Upload
 ↓
Storage
 ↓
Job Queue
 ↓
Worker
 ↓
Parse
 ↓
Chunk
 ↓
Embed
 ↓
Index
```

Initial implementation may remain simple but must expose processing status.

---

# 48. Persistence

Recommended:

```text
PostgreSQL
pgvector
Object Storage
Redis
```

Redis roles:

```text
queue
cache
rate limiting
```

Do not add Redis unless those features are actually implemented.

---

# 49. Suggested Database Tables

```text
users
workspaces

prompts
prompt_versions
prompt_executions

documents
document_chunks

retrieval_runs
retrieval_results

favorites

eval_datasets
eval_cases
eval_runs
eval_results
```

Not every table is required in first migration.

---

# 50. Retrieval Logging

For debugging/evaluation, optionally store:

```text
query
strategy
candidate IDs
candidate ranks
RRF ranks
reranker scores
selected chunks
latency
model versions
```

Respect privacy and retention settings.

---

# 51. Authentication

MVP options:

```text
email/password
Google OAuth
```

All private resources require ownership checks.

---

# 52. Security Requirements

Minimum:

- authentication,
- authorization,
- secure file validation,
- rate limits,
- upload limits,
- secrets outside source code,
- database ownership checks,
- sanitized errors,
- prompt injection isolation,
- dependency updates.

---

# 53. Privacy Requirements

Users must be able to delete:

```text
prompts
executions
documents
document chunks
```

Deletion behavior must be clearly defined.

Avoid indefinite storage of unnecessary provider payloads.

---

# 54. Observability

Measure:

```text
intent latency
prompt compile latency
document processing time
embedding latency
retrieval latency
reranking latency
generation latency
retrieval candidate count
context token count
provider errors
```

---

# 55. Performance Targets

Initial targets, not hard guarantees:

```text
Prompt analysis:
interactive latency

Prompt compilation:
interactive latency

Retrieval:
sub-second to low-second range at MVP scale

Document ingestion:
asynchronous

UI:
no blocking page refresh for normal flows
```

Benchmark before claiming performance numbers publicly.

---

# 56. Testing Strategy

## Unit

```text
PromptSpec validation
intent parsing helpers
gap logic
compilers
chunking
RRF
context builder
citation formatting
```

## Integration

```text
database
document ingestion
vector search
hybrid retrieval
prompt execution
authorization
```

## Evaluation

```text
retrieval quality
generation grounding
prompt variants
```

---

# 57. Provider Abstraction

Core business logic must not depend directly on one LLM provider.

Conceptual interfaces:

```ts
LLMProvider
EmbeddingProvider
RerankerProvider
PromptCompiler
```

Provider implementations live at infrastructure boundaries.

---

# 58. Failure Behavior

Examples:

### LLM failure

```text
retry if appropriate
→ normalized application error
```

### Embedding failure

```text
mark document processing failed
→ allow retry
```

### No retrieval result

```text
do not invent document evidence
→ tell user insufficient information was found
```

### Reranker unavailable

```text
optionally fall back to fused retrieval result
```

---

# 59. Cost Control

Important because each request may otherwise cause many model calls.

Strategies:

- avoid LLM calls for deterministic tasks,
- combine intent + gap extraction where reliable,
- batch embeddings,
- cache reusable results,
- do not rewrite trivial queries,
- rerank only limited candidates,
- avoid repeated document embeddings,
- use token budgets,
- store compiled PromptSpec when reusable.

---

# 60. Target LLM Call Flow

Typical prompt generation should ideally require:

```text
1 call:
Intent + PromptSpec + Gap Detection
```

Then:

```text
0 calls if clarification needed until user responds
```

Compilation should preferably be deterministic or inexpensive where possible.

Avoid chains of 5–10 LLM calls for ordinary requests.

---

# 61. RAG Cost Flow

```text
Document ingestion:
parse
→ chunk
→ batched embedding
→ index

Query:
embedding
→ SQL retrieval
→ optional rewrite
→ optional rerank
→ generation
```

Only invoke expensive stages when they improve expected quality.

---

# 62. MVP Milestones

## M0 — Foundation

- monorepo
- frontend
- API
- DB
- authentication
- CI
- environment configuration

## M1 — Prompt Engine

- PromptSpec
- intent analysis
- gap analysis
- compiler
- TR/EN
- preview

## M2 — Execution

- run prompt
- execution history
- errors
- usage tracking

## M3 — Documents

- uploads
- parsing
- storage
- processing jobs
- chunking

## M4 — RAG Baseline

- embeddings
- pgvector
- HNSW
- dense retrieval
- citations

## M5 — Advanced RAG

- sparse retrieval
- RRF
- reranker
- query processing
- context builder

## M6 — Evaluation

- labeled dataset
- retrieval metrics
- ablation experiments
- reports

## M7 — Product Polish

- history
- favorites
- document management
- quality indicators
- responsive UX
- README/demo

---

# 63. MVP Acceptance Criteria

A user can:

1. create an account,
2. enter a vague request,
3. choose Turkish or English,
4. receive at most a few relevant clarification questions,
5. obtain an optimized prompt,
6. edit/copy/run it,
7. upload a document,
8. ask a question grounded in the document,
9. inspect supporting sources,
10. revisit previous prompts.

Developer can:

1. run the project locally,
2. run migrations,
3. run tests,
4. run retrieval evaluations,
5. compare retrieval strategies,
6. understand the architecture from documentation.

---

# 64. RAG Acceptance Criteria

The RAG implementation is not considered complete merely because answers look good.

It should demonstrate:

```text
✓ document parsing
✓ structured chunking
✓ embeddings
✓ HNSW indexing
✓ dense retrieval
✓ sparse retrieval
✓ RRF fusion
✓ metadata filtering
✓ reranking
✓ context construction
✓ citations
✓ ownership isolation
✓ evaluation dataset
✓ measurable retrieval metrics
✓ ablation comparison
```

---

# 65. README Evidence

The public repository should eventually include:

```text
architecture diagram
RAG pipeline diagram
example PromptSpec
example retrieval trace
evaluation methodology
metric table
setup instructions
screenshots/demo
known limitations
future work
```

Avoid unsupported marketing claims.

---

# 66. Portfolio Value

The project should visibly demonstrate that the developer understands:

```text
LLM orchestration
structured outputs
prompt compilation
retrieval systems
vector search
lexical search
ranking
reranking
RAG evaluation
backend architecture
database design
security
product UX
```

The project must not appear to be only:

```text
UI
+
one OpenAI API call
```

---

# 67. Explicit Non-Goals for MVP

Do not prioritize:

```text
autonomous agents
multi-agent orchestration
voice assistants
custom foundation-model training
custom vector database
distributed microservices
Kubernetes
mobile native apps
enterprise SSO
prompt marketplace
real-time collaboration
```

These may be reconsidered only after the core product is stable.

---

# 68. Architectural Invariants

These rules should remain true:

1. `PromptSpec` is model-independent.
2. Prompt compilers are provider-specific adapters.
3. RAG is modular and independently evaluable.
4. Retrieval is not embedded inside generation code.
5. Authorization is enforced before retrieval.
6. Citations derive from actual retrieved chunks.
7. Uploaded content is treated as untrusted.
8. Retrieval improvements are measured.
9. Expensive AI calls are justified.
10. Product simplicity for users is preserved even when backend architecture is sophisticated.

---

# 69. Final Product Principle

Internally the system may contain:

```text
intent classification
structured schemas
hybrid retrieval
RRF
reranking
query rewriting
context construction
evaluation
```

The user should still experience:

```text
Tell us what you want.
Attach something if relevant.
Get a better prompt.
Run it.
```

Complexity belongs in the system, not in the user's workflow.


# 70. Templates & Cold-Start UX

The product must reduce blank-page friction for users who do not know what to ask.

The create experience should provide optional quick-start presets.

Initial categories may include:

```text
Write an Email
Summarize Something
Explain Something
Compare Options
Analyze a Document
Brainstorm Ideas
Plan Something
Get Coding Help
```

Turkish UI examples:

```text
E-posta Yaz
Özet Çıkar
Bir Şeyi Açıkla
Karşılaştır
Belge Analiz Et
Fikir Üret
Plan Oluştur
Kodlama Yardımı
```

Templates are not fixed final prompts.

They initialize context for the Prompt Engine.

Preferred architecture:

```text
TaskPreset
    +
User Request
    ↓
Intent Analyzer
    ↓
PromptSpec
    ↓
Gap Analyzer
    ↓
Compiler
```

---

# 71. TaskPreset Model

Suggested structure:

```ts
interface TaskPreset {
  id: string;
  category: string;

  title: {
    tr: string;
    en: string;
  };

  description?: {
    tr: string;
    en: string;
  };

  promptSpecHints: Partial<PromptSpec>;

  suggestedFields?: string[];

  isActive: boolean;
  sortOrder: number;
}
```

Example:

```json
{
  "id": "business-email",
  "category": "writing",
  "promptSpecHints": {
    "task": {
      "type": "writing.email"
    },
    "output": {
      "format": "email"
    }
  }
}
```

Preset hints are defaults only.

Explicit user intent overrides preset values.

---

# 72. Cold-Start Create Experience

The create page should support both:

```text
Quick Start
+
Free Text
```

Suggested desktop flow:

```text
┌──────────────────────────────────────────┐
│ What would you like to do?              │
│                                          │
│ [Write Email] [Summarize] [Explain]     │
│ [Compare]     [Analyze]   [More...]      │
│                                          │
│ Or describe anything:                    │
│ ┌──────────────────────────────────────┐ │
│ │ ...                                  │ │
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

Selecting a preset must not lock the user into that category.

The user may freely modify the request afterward.

---

# 73. User Feedback

Users should be able to provide lightweight feedback on generated or executed outputs.

Minimum explicit feedback:

```text
👍 Positive
👎 Negative
```

Optional follow-up reasons may include:

```text
Did not understand my request
Incorrect result
Missing information
Too long
Too short
Wrong tone
Poor formatting
Other
```

Reasons must be localized for Turkish and English.

Feedback should require minimal friction.

---

# 74. Feedback Data Model

Suggested structure:

```ts
interface PromptFeedback {
  id: string;
  userId: string;

  promptId?: string;
  promptVersionId?: string;
  executionId?: string;

  rating?: "positive" | "negative";
  reason?: string;
  comment?: string;

  generatedPromptEdited?: boolean;
  editDistance?: number;

  rerunCount?: number;
  regenerationCount?: number;

  createdAt: Date;
}
```

Feedback must remain associated with the exact prompt/execution version where possible.

---

# 75. Product Learning Policy

Feedback exists to improve the product, but must not automatically be interpreted as labeled truth.

Initial uses:

```text
identify common failure modes
compare task categories
find poor clarification behavior
improve templates
improve PromptSpec extraction
improve compiler rules
build manually reviewed evaluation datasets
```

Potential implicit signals:

```text
large prompt edits
multiple regenerations
multiple reruns
favorite/save
immediate execution
abandonment
```

These signals are ambiguous.

Example:

```text
Large edit ≠ automatically bad generation
Favorite ≠ automatically perfect generation
Rerun ≠ automatically failure
```

Future fine-tuning requires a separately curated and validated dataset.

---

# 76. Rate Limiting

Rate limiting protects system availability and prevents abuse.

It is independent from product usage quotas.

Possible dimensions:

```text
requests per IP
requests per authenticated user
requests per endpoint
```

Sensitive/high-cost routes may use stricter limits.

Examples:

```text
prompt execution
document upload
document processing
retrieval search
```

Exact values must remain configurable and should not be defined permanently in this specification.

---

# 77. Usage Quotas & Cost Guardrails

Usage quotas protect against uncontrolled provider and infrastructure costs.

Possible quota dimensions:

```text
prompt generations per period
prompt executions per period
model tokens per period
document uploads per period
processed document pages
embedding usage
storage bytes
```

Quotas may vary by:

```text
plan
user
workspace
environment
```

Architecture:

```text
Request
   ↓
Authentication
   ↓
Rate Limiter
   ↓
Quota / Usage Policy
   ↓
Authorization
   ↓
Application Service
   ↓
Usage Accounting
```

Do not permanently encode example numeric limits into business logic.

---

# 78. Usage Policy Model

Conceptual model:

```ts
interface UsageLimits {
  promptGenerationsPerDay?: number;
  promptExecutionsPerDay?: number;

  monthlyModelTokens?: number;

  documentUploadsPerDay?: number;
  monthlyProcessedPages?: number;

  storageBytes?: number;
}
```

A future plan model may contain:

```text
FREE
PRO
TEAM
```

Plans are not required for MVP.

The architecture should only make future plan-based limits possible.

---

# 79. Usage Events

Important resource-consuming actions should create normalized usage records.

Suggested event types:

```text
PROMPT_GENERATION
PROMPT_EXECUTION
LLM_INPUT_TOKENS
LLM_OUTPUT_TOKENS
DOCUMENT_UPLOAD
DOCUMENT_PAGE_PROCESSED
EMBEDDING_USAGE
STORAGE_USAGE
```

Possible entity:

```ts
interface UsageEvent {
  id: string;
  userId: string;
  workspaceId?: string;

  type: string;
  quantity: number;

  provider?: string;
  model?: string;

  promptId?: string;
  documentId?: string;

  createdAt: Date;
}
```

Server-side records are authoritative.

---

# 80. User-Facing Error Experience

Technical failures must be translated into simple, localized UI states.

Users should never need to understand:

```text
HTTP status codes
embedding providers
vector databases
LLM gateways
rerankers
stack traces
```

Preferred error architecture:

```text
Infrastructure Failure
        ↓
Stable App Error Code
        ↓
Localized UX Message
```

Example:

```text
OPENAI / provider timeout
        ↓
LLM_PROVIDER_TIMEOUT
        ↓
TR:
"İşlem şu anda tamamlanamadı. Tekrar deneyebilirsin."

EN:
"We couldn't complete this request right now. Please try again."
```

---

# 81. Error Message Principles

User-facing errors must be:

```text
clear
brief
actionable
non-technical
honest
localized
```

Do not fabricate causes.

Bad:

> The AI servers are overloaded.

when this is not known.

Good:

> We couldn't complete this request right now. Please try again.

If retry is not appropriate, provide the next valid action.

Example:

```text
Unsupported document:
"This file type isn't supported yet. Upload a PDF, DOCX, TXT, or Markdown file."
```

---

# 82. Error UX States

The frontend should distinguish at least:

```text
retryable temporary failure
validation failure
quota reached
rate limited
document processing failure
authorization failure
unsupported input
no relevant document evidence
```

Examples:

### Temporary failure

```text
Couldn't complete the request.
[Try Again]
```

### Quota reached

```text
You've reached your current usage limit.
```

### Document processing failure

```text
We couldn't process this document.
[Try Again] [Remove Document]
```

### No RAG evidence

```text
We couldn't find enough information in the selected documents to answer reliably.
```

Do not convert missing retrieval evidence into a generic system error.

---

# 83. Database Additions

The evolving schema may include:

```text
task_presets
prompt_feedback
usage_events
usage_policies
```

Optional future tables:

```text
plans
plan_limits
feedback_reasons
```

Do not create future-only tables until required.

---

# 84. Updated MVP Feature Set

MVP should now include:

```text
authentication
Turkish / English
quick-start task presets
free-text task input
intent analysis
PromptSpec
gap analysis
dynamic clarification
prompt compilation
prompt preview/editing
copy prompt
direct execution
prompt history
favorites
basic explicit feedback
document upload
RAG retrieval
citations
rate limiting
configurable usage guardrails
localized user-facing errors
retrieval evaluation framework
```

Advanced feedback analytics remain post-MVP.

---

# 85. Updated Create Screen

Desktop concept:

```text
┌──────────────────────────────────────────────┐
│ PromptForge                                  │
├───────────────────┬──────────────────────────┤
│ Quick Start       │                          │
│ [Email] [Explain] │ Generated Prompt         │
│ [Summary] [...]   │                          │
│                   │ Live Preview             │
│ User Request      │                          │
│                   │                          │
│ Clarifications    │                          │
│                   │                          │
│ Documents         │                          │
├───────────────────┴──────────────────────────┤
│ Copy        Improve        Run Prompt         │
└──────────────────────────────────────────────┘
```

After execution:

```text
Result

[👍] [👎]

Optional:
Tell us what could be better.
```

Feedback must not obstruct the primary workflow.

---

# 86. Updated Observability

In addition to existing technical metrics, track aggregated product signals where privacy rules allow:

```text
preset usage
prompt generation count
execution count
regeneration count
feedback rate
positive/negative feedback ratio
quota rejection count
rate-limit rejection count
document-processing failure rate
```

Do not treat product telemetry as ground-truth model quality metrics.

---

# 87. Updated Cost-Control Strategy

Cost control consists of four layers:

```text
1. Efficient architecture
2. Rate limiting
3. Usage quotas
4. Usage observability
```

Efficient architecture includes:

```text
avoid unnecessary LLM calls
batch embeddings
cache reusable results
conditional query rewriting
limited reranking candidates
token budgets
duplicate-document detection
```

Rate limits protect service stability.

Quotas protect financial exposure.

Observability identifies abnormal usage.

---

# 88. Updated MVP Acceptance Criteria

In addition to previous acceptance criteria, a user can:

1. start from a quick preset instead of a blank page,
2. modify preset-assisted requests freely,
3. provide positive or negative feedback,
4. receive understandable Turkish or English error messages,
5. retry recoverable failures,
6. be prevented from uncontrolled high-cost usage through configurable limits.

The system must:

1. distinguish rate limits from usage quotas,
2. record authoritative server-side usage,
3. avoid exposing raw provider errors,
4. avoid fabricating failure causes,
5. keep feedback linked to the relevant prompt/execution,
6. treat feedback as a signal rather than automatic ground truth.

---

# 89. Updated Product Principle

The system should become more sophisticated without exposing that sophistication to the user.

Internally:

```text
PromptSpec
hybrid retrieval
reranking
usage accounting
feedback telemetry
error taxonomy
quota policies
```

Externally:

```text
Choose what you want to do.
Describe it naturally.
Attach something if needed.
Get a better prompt.
Run it.
```

Templates reduce friction.

Feedback improves future decisions.

Guardrails control cost.

Error handling preserves trust.

The product remains simple.
