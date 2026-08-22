"""add production document embeddings

Revision ID: 202608220007
Revises: 202608220006
Create Date: 2026-08-22 05:00:00
"""

from alembic import op

revision = "202608220007"
down_revision = "202608220006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        (
            "ingestion_status IN ('uploaded', 'processing', 'parsed', 'chunking', "
            "'chunked', 'embedding', 'embedded', 'ready', 'failed')"
        ),
    )
    op.execute(
        """
        CREATE TABLE document_embeddings (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(128) NOT NULL,
            document_id VARCHAR(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_id VARCHAR(36) NOT NULL REFERENCES document_chunks(id) ON DELETE CASCADE,
            embedding vector(1024) NOT NULL,
            embedding_model_id VARCHAR(255) NOT NULL,
            embedding_dimension INTEGER NOT NULL,
            embedded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_document_embeddings_chunk_id UNIQUE (chunk_id)
        )
        """
    )
    op.create_index("ix_document_embeddings_workspace_id", "document_embeddings", ["workspace_id"])
    op.create_index("ix_document_embeddings_document_id", "document_embeddings", ["document_id"])
    op.execute(
        """
        CREATE INDEX ix_document_embeddings_embedding_hnsw
        ON document_embeddings USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_embeddings_embedding_hnsw")
    op.drop_index("ix_document_embeddings_document_id", table_name="document_embeddings")
    op.drop_index("ix_document_embeddings_workspace_id", table_name="document_embeddings")
    op.drop_table("document_embeddings")
    op.drop_constraint("ck_documents_ingestion_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_ingestion_status",
        "documents",
        (
            "ingestion_status IN ('uploaded', 'processing', 'parsed', 'chunking', "
            "'chunked', 'ready', 'failed')"
        ),
    )
