"""Add review_cases table for Human Review / Exception Resolution

Creates a durable, queryable review-case table. Deliberately NOT trigger-
protected as immutable (unlike journey_snapshots/audit_events) since a
review case's own status genuinely mutates in place (claim/resolve/
escalate) - the audit trail of what happened to it lives in the existing
append-only audit_events table via new REVIEW_CASE_* event types, not here.

Revision ID: 004_review_cases
Revises: 003_journey_natural_language
Create Date: 2026-09-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_review_cases"
down_revision: str | None = "003_journey_natural_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_cases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("case_seq", sa.Integer(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("context_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reason_title", sa.String(length=300), nullable=False),
        sa.Column("reason_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="MEDIUM"),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="REVIEW_REQUIRED"
        ),
        sa.Column("case_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("assigned_reviewer", sa.String(length=200), nullable=True),
        sa.Column("review_lock_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_type", sa.String(length=50), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("requested_information", sa.JSON(), nullable=True),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resulting_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["context_snapshot_id"], ["journey_snapshots.id"]),
        sa.ForeignKeyConstraint(["resulting_snapshot_id"], ["journey_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journey_id", "dedupe_key", name="uq_review_case_journey_dedupe"),
        sa.UniqueConstraint("case_seq", name="uq_review_case_seq"),
    )
    op.create_index(
        "idx_review_cases_status_created", "review_cases", ["status", "created_at"]
    )
    op.create_index("idx_review_cases_journey", "review_cases", ["journey_id"])
    op.create_index(
        op.f("ix_review_cases_session_id"), "review_cases", ["session_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_cases_session_id"), table_name="review_cases")
    op.drop_index("idx_review_cases_journey", table_name="review_cases")
    op.drop_index("idx_review_cases_status_created", table_name="review_cases")
    op.drop_table("review_cases")
