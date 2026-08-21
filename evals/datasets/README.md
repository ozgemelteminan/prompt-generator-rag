# Chunking evaluation dataset v1

This static, manually reviewable dataset contains six short documents (three Turkish,
three English) and 42 queries. Source documents are represented as ordered blocks so
ground truth can refer to stable block IDs, not strategy-specific chunk IDs.

A retrieved chunk is relevant when its `source_block_ids` intersects a query's
`relevantBlockIds`. Categories are factual, paraphrase, heading_dependent,
cross_paragraph, terminology_mismatch, and morphology_heavy. The latter includes
Turkish inflection/surface-form variation; labels remain reviewable rather than being
treated as automatically generated truth.
