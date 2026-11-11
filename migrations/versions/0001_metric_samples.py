"""Create the metric samples table.

Revision ID: 0001_metric_samples
Revises:
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_metric_samples"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_samples",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("cpu_usage_percent", sa.Float(), nullable=False),
        sa.Column("memory_usage_percent", sa.Float(), nullable=False),
        sa.Column("disk_usage_percent", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_metric_samples_collected_at",
        "metric_samples",
        ["collected_at"],
        unique=False,
    )
    op.create_index(
        "ix_metric_samples_hostname_collected_at",
        "metric_samples",
        ["hostname", "collected_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_metric_samples_hostname_collected_at", table_name="metric_samples")
    op.drop_index("ix_metric_samples_collected_at", table_name="metric_samples")
    op.drop_table("metric_samples")
