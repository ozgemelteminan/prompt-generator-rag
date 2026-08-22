# Architecture

PromptForge keeps prompt construction and document intelligence as distinct
application paths behind the same FastAPI boundary.

```mermaid
flowchart TB
    User[User] --> Web[Next.js Web]
    Web --> API[FastAPI API]

    subgraph Prompt_path[Structured prompt path]
        API --> Intent[Intent Analysis]
        Intent --> Spec[Canonical PromptSpec]
        Spec --> Gaps[Gap Analysis]
        Gaps --> Compiler[Deterministic Prompt Compiler]
        Compiler --> Prompt[Optimized Prompt]
        Prompt -. optional .-> Execution[Provider Execution]
    end

    subgraph Document_RAG_path[Document intelligence path]
        API --> Upload[Upload and Validate]
        Upload --> Parse[Parse and Normalize]
        Parse --> Chunk[Structure-aware Chunking]
        Chunk --> Embed[Multilingual E5 Embedding]
        Embed --> Vector[(PostgreSQL + pgvector)]
        API --> Query[Question]
        Query --> Retrieve[Dense Retrieval]
        Vector --> Retrieve
        Retrieve --> Context[Context Builder]
        Context --> Generate[Grounded Generation]
        Generate --> Citations[Citation Validation]
    end
```

The production retrieval configuration is
`StructureAwareChunker(350/500/40) → intfloat/multilingual-e5-large-instruct →
PostgreSQL + pgvector dense retrieval`. See the README for its measured M4
selection evidence and the final evaluation artifact for limitations.
