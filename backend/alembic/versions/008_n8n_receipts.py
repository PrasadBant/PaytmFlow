"""Receiver-side claims for the n8n workflow

The n8n workflow claims each event_id here before it sends a notification.
The primary key on event_id makes the claim atomic (INSERT ... ON CONFLICT DO
NOTHING), so concurrent or repeated deliveries of one event notify at most
once. New table only; nothing existing is touched.

Revision ID: 008_n8n_receipts
Revises: 007_n8n_outbox
Create Date: 2026-10-04 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008_n8n_receipts"
down_revision: str | None = "007_n8n_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "n8n_receipts",
        sa.Column("event_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=50), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_n8n_receipts_status_claimed", "n8n_receipts", ["status", "claimed_at"])


def downgrade() -> None:
    op.drop_index("idx_n8n_receipts_status_claimed", table_name="n8n_receipts")
    op.drop_table("n8n_receipts")
