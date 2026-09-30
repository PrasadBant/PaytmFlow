"""Durable n8n delivery-failure records

Events that exhaust their bounded retries, or that n8n permanently rejects,
are kept here (payload included) so they can be inspected and redelivered
with the same event_id instead of being dropped after a log line.

Revision ID: 006_notification_failures
Revises: 005_evidence_provider
Create Date: 2026-09-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006_notification_failures"
down_revision: str | None = "005_evidence_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_failures",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("journey_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("failure_kind", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_notification_failures_journey_id", "notification_failures", ["journey_id"])
    op.create_index(
        "idx_notification_failures_pending",
        "notification_failures",
        ["delivered_at", "failure_kind"],
    )


def downgrade() -> None:
    op.drop_index("idx_notification_failures_pending", table_name="notification_failures")
    op.drop_index("ix_notification_failures_journey_id", table_name="notification_failures")
    op.drop_table("notification_failures")
