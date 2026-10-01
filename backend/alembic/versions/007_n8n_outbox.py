"""Turn notification_failures into the n8n transactional outbox

Every n8n event is now written in the same transaction as the business change
that emits it (not only after delivery fails), then claimed by a dispatcher
under a lease. Existing rows are carried over: undelivered transient failures
become PENDING, delivered ones DELIVERED, permanent ones stay PERMANENT.

Downgrade restores the 006 shape. It is lossy by design: EXPIRED rows become
PERMANENT, and PENDING rows that never failed appear as transient failures.

Revision ID: 007_n8n_outbox
Revises: 006_notification_failures
Create Date: 2026-10-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_n8n_outbox"
down_revision: str | None = "006_notification_failures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_notification_failures_pending", table_name="notification_failures")
    op.rename_table("notification_failures", "n8n_outbox")
    op.execute("ALTER INDEX ix_notification_failures_journey_id RENAME TO ix_n8n_outbox_journey_id")
    op.execute("ALTER INDEX notification_failures_pkey RENAME TO n8n_outbox_pkey")
    op.alter_column("n8n_outbox", "failure_kind", new_column_name="status")
    op.execute(
        "UPDATE n8n_outbox SET status = CASE "
        "WHEN delivered_at IS NOT NULL THEN 'DELIVERED' "
        "WHEN status = 'PERMANENT' THEN 'PERMANENT' "
        "ELSE 'PENDING' END"
    )
    op.add_column(
        "n8n_outbox",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column("n8n_outbox", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("n8n_outbox", sa.Column("lease_token", sa.String(length=32), nullable=True))
    op.add_column("n8n_outbox", sa.Column("redacted_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("n8n_outbox", "attempts", server_default=sa.text("0"))
    op.alter_column("n8n_outbox", "last_error", server_default=sa.text("''"))
    op.create_index("idx_n8n_outbox_due", "n8n_outbox", ["status", "next_attempt_at"])
    op.create_index("idx_n8n_outbox_status_updated", "n8n_outbox", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_n8n_outbox_status_updated", table_name="n8n_outbox")
    op.drop_index("idx_n8n_outbox_due", table_name="n8n_outbox")
    op.alter_column("n8n_outbox", "last_error", server_default=None)
    op.alter_column("n8n_outbox", "attempts", server_default=None)
    op.drop_column("n8n_outbox", "redacted_at")
    op.drop_column("n8n_outbox", "lease_token")
    op.drop_column("n8n_outbox", "lease_until")
    op.drop_column("n8n_outbox", "next_attempt_at")
    op.execute(
        "UPDATE n8n_outbox SET status = CASE "
        "WHEN status IN ('PERMANENT', 'EXPIRED') AND delivered_at IS NULL THEN 'PERMANENT' "
        "ELSE 'TRANSIENT_EXHAUSTED' END"
    )
    op.alter_column("n8n_outbox", "status", new_column_name="failure_kind")
    op.execute("ALTER INDEX n8n_outbox_pkey RENAME TO notification_failures_pkey")
    op.execute("ALTER INDEX ix_n8n_outbox_journey_id RENAME TO ix_notification_failures_journey_id")
    op.rename_table("n8n_outbox", "notification_failures")
    op.create_index(
        "idx_notification_failures_pending",
        "notification_failures",
        ["delivered_at", "failure_kind"],
    )
