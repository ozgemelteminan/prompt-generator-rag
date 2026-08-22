# M4 final recommendation

## 1. Selected chunker

Production `StructureAwareChunker`: target 350, maximum 500, overlap 40 tokens.

## 2. Selected embedding

`intfloat/multilingual-e5-large-instruct`.

## 3. Selected retrieval architecture

Dense-only: StructureAwareChunker → multilingual E5 → dense retrieval.

## 4. RRF decision

Do not make RRF the M5 default: the measured ranking gain is small, recall is unchanged, and no Dense miss was recovered.

Measured Hybrid − Dense: MRR +0.0074; nDCG@10 +0.0052; Recall@10 +0.0000; TR MRR +0.0214; EN MRR -0.0067.

## 5. Reranker decision

Exclude BAAI/bge-reranker-v2-m3 from M5: this tested configuration reduced Recall@5 and nDCG@10.

This conclusion is limited to the tested candidate depth, dataset, and configuration; it does not claim that reranking never works.

## 6. Exact M5 configuration

StructureAwareChunker (350/500/40) → multilingual-e5-large-instruct → dense retrieval. Keep BM25/RRF behind evaluation-only validation, and do not include the tested reranker.

## 7. Evidence summary

E5 was the measured M4.2 MRR leader. Dense E5 beat standalone BM25 in M4.3. M4.4 Hybrid improved ranking metrics slightly but did not improve recall or recover a Dense miss; without production latency evidence, the simpler Dense default is the defensible choice.

## 8. Known limitations

- retrieval_eval_v1 has 84 manually reviewable Turkish/English queries; it is not a production traffic sample.
- Ground truth uses source-block relevance, which can create recall ceilings and does not measure answer quality.
- No production latency or cost benchmark has been run.
- BM25 has no Turkish morphology or stemming analyzer.
- Only BAAI/bge-reranker-v2-m3 was tested; this does not generalize to all rerankers.
- No statistical significance analysis was performed.

## 9. What M5 should implement

Production support for the selected Dense configuration, plus measurement hooks and a larger held-out evaluation before reconsidering Hybrid RRF.

## 10. What M5 should NOT implement

Do not ship the tested reranker, production BM25/RRF, query rewriting, context building, citations, or generation solely from these M4 results.
