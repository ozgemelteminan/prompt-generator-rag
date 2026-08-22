"""Relational persistence models for saved prompt work."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.vector import PgVector
from app.infrastructure.huggingface_embeddings import SELECTED_EMBEDDING_DIMENSION


class Base(DeclarativeBase):
    """Base for application-owned relational tables."""


class PromptGenerationRecord(Base):
    __tablename__ = "prompt_generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Auth is not implemented; null records belong to the current local installation.
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    original_input: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    preset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_spec: Mapped[dict[str, object]] = mapped_column(JSON)
    generation_state: Mapped[str] = mapped_column(String(32))
    compiled_prompt: Mapped[str] = mapped_column(Text)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    executions: Mapped[list["PromptExecutionRecord"]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["PromptFeedbackRecord"]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan"
    )


class PromptExecutionRecord(Base):
    __tablename__ = "prompt_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_generations.id", ondelete="CASCADE"), index=True
    )
    output: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prompt: Mapped[PromptGenerationRecord] = relationship(back_populates="executions")
    feedback: Mapped[list["PromptFeedbackRecord"]] = relationship(back_populates="execution")


class PromptFeedbackRecord(Base):
    __tablename__ = "prompt_feedback"
    __table_args__ = (
        CheckConstraint("rating IN ('positive', 'negative')", name="ck_prompt_feedback_rating"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt_id: Mapped[str] = mapped_column(
        ForeignKey("prompt_generations.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("prompt_executions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prompt: Mapped[PromptGenerationRecord] = relationship(back_populates="feedback")
    execution: Mapped[PromptExecutionRecord | None] = relationship(back_populates="feedback")


class UsageCounterRecord(Base):
    __tablename__ = "usage_counters"

    caller_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    period_key: Mapped[str] = mapped_column(String(7), primary_key=True)
    used_amount: Mapped[int] = mapped_column(default=0, server_default="0")
    reserved_amount: Mapped[int] = mapped_column(default=0, server_default="0")
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UsageEventRecord(Base):
    __tablename__ = "usage_events"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_usage_events_positive_amount"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    caller_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[int] = mapped_column(default=1)
    prompt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            (
                "ingestion_status IN ('uploaded', 'processing', 'parsed', 'chunking', "
                "'chunked', 'embedding', 'embedded', 'ready', 'failed')"
            ),
            name="ck_documents_ingestion_status",
        ),
        CheckConstraint("file_size > 0", name="ck_documents_positive_file_size"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    ingestion_status: Mapped[str] = mapped_column(String(16), default="uploaded")
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    blocks: Mapped[list["DocumentBlockRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["DocumentChunkRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    embeddings: Mapped[list["DocumentEmbeddingRecord"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentBlockRecord(Base):
    __tablename__ = "document_blocks"
    __table_args__ = (
        CheckConstraint("order_index >= 0", name="ck_document_blocks_nonnegative_order"),
        UniqueConstraint("document_id", "order_index", name="uq_document_blocks_document_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column()
    block_type: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(nullable=True)
    heading_level: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[DocumentRecord] = relationship(back_populates="blocks")


class DocumentChunkRecord(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="ck_document_chunks_nonnegative_index"),
        CheckConstraint("token_count > 0", name="ck_document_chunks_positive_token_count"),
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_index"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column()
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    page_start: Mapped[int | None] = mapped_column(nullable=True)
    page_end: Mapped[int | None] = mapped_column(nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_block_start: Mapped[int] = mapped_column()
    source_block_end: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[DocumentRecord] = relationship(back_populates="chunks")
    embedding: Mapped["DocumentEmbeddingRecord | None"] = relationship(
        back_populates="chunk", cascade="all, delete-orphan", uselist=False
    )


class DocumentEmbeddingRecord(Base):
    __tablename__ = "document_embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", name="uq_document_embeddings_chunk_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(128), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True
    )
    embedding: Mapped[list[float]] = mapped_column(PgVector(SELECTED_EMBEDDING_DIMENSION))
    embedding_model_id: Mapped[str] = mapped_column(String(255))
    embedding_dimension: Mapped[int] = mapped_column()
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    document: Mapped[DocumentRecord] = relationship(back_populates="embeddings")
    chunk: Mapped[DocumentChunkRecord] = relationship(back_populates="embedding")
