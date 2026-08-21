"""add usage accounting

Revision ID: 202608210003
Revises: 202608210002
Create Date: 2026-08-21 00:00:00

"""

import sqlalchemy as sa

from alembic import op

revision = "202608210003"
down_revision = "202608210002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_counters",
        sa.Column("caller_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("used_amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("caller_id", "event_type", "period_key"),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("caller_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("prompt_id", sa.String(length=36), nullable=True),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount > 0", name="ck_usage_events_positive_amount"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_caller_id", "usage_events", ["caller_id"])
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_caller_id", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_table("usage_counters")
