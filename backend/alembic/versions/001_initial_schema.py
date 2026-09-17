"""Initial schema with 8 tables, indexes, constraints, and immutability triggers

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-01 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. sessions
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # 2. journeys (before snapshots to allow foreign keys, current_snapshot_id nullable initially)
    op.create_table(
        "journeys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("journey_type", sa.String(length=50), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("readiness", sa.String(length=50), nullable=False),
        sa.Column("current_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("goal", sa.JSON(), nullable=False),
        sa.Column("display_title", sa.String(length=200), nullable=False),
        sa.Column("display_summary", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_journeys_session_updated", "journeys", ["session_id", "updated_at"], unique=False
    )
    op.create_index(
        "idx_journeys_type_updated", "journeys", ["journey_type", "updated_at"], unique=False
    )
    op.create_index(
        "idx_journeys_status_updated", "journeys", ["status", "updated_at"], unique=False
    )

    # 3. journey_snapshots
    op.create_table(
        "journey_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("previous_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("readiness", sa.String(length=50), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("goal", sa.JSON(), nullable=False),
        sa.Column("pending_clarification", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["journey_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journey_id", "version_number", name="uq_snapshots_journey_version"),
        sa.UniqueConstraint(
            "journey_id", "previous_snapshot_id", name="uq_snapshots_journey_prev_snapshot"
        ),
    )
    op.create_index(
        "idx_snapshots_journey_created",
        "journey_snapshots",
        ["journey_id", "created_at"],
        unique=False,
    )

    # Add foreign key from journeys.current_snapshot_id to journey_snapshots.id
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("journeys") as batch_op:
            batch_op.create_foreign_key(
                "fk_journey_current_snapshot",
                "journey_snapshots",
                ["current_snapshot_id"],
                ["id"],
            )
    else:
        op.create_foreign_key(
            "fk_journey_current_snapshot",
            "journeys",
            "journey_snapshots",
            ["current_snapshot_id"],
            ["id"],
        )

    # 4. evidence
    op.create_table(
        "evidence",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_data", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_evidence_journey_created", "evidence", ["journey_id", "created_at"], unique=False
    )
    op.create_index("idx_evidence_sha256", "evidence", ["sha256"], unique=False)

    # 5. clarifications
    op.create_table(
        "clarifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("ambiguity_id", sa.String(length=100), nullable=False),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_type", sa.String(length=50), nullable=False),
        sa.Column("user_response", sa.JSON(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 6. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("action_id", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("key"),
    )

    # 7. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("journey_id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_audit_events_journey_created",
        "audit_events",
        ["journey_id", "created_at"],
        unique=False,
    )
    op.create_index("idx_audit_events_event_type", "audit_events", ["event_type"], unique=False)

    # 8. packs_metadata
    op.create_table(
        "packs_metadata",
        sa.Column("journey_type", sa.String(length=50), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=False),
        sa.Column("flagship_demo", sa.Boolean(), nullable=False),
        sa.Column("manifest_yaml", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("journey_type"),
    )

    # Postgres Immutability Triggers
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'immutable table: %', TG_TABLE_NAME; END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER no_update_snapshots BEFORE UPDATE OR DELETE ON journey_snapshots
              FOR EACH ROW EXECUTE FUNCTION reject_mutation();

            CREATE TRIGGER no_update_audit BEFORE UPDATE OR DELETE ON audit_events
              FOR EACH ROW EXECUTE FUNCTION reject_mutation();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS no_update_snapshots ON journey_snapshots;")
        op.execute("DROP TRIGGER IF EXISTS no_update_audit ON audit_events;")
        op.execute("DROP FUNCTION IF EXISTS reject_mutation;")

    op.drop_table("packs_metadata")
    op.drop_index("idx_audit_events_event_type", table_name="audit_events")
    op.drop_index("idx_audit_events_journey_created", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("idempotency_keys")
    op.drop_table("clarifications")
    op.drop_index("idx_evidence_sha256", table_name="evidence")
    op.drop_index("idx_evidence_journey_created", table_name="evidence")
    op.drop_table("evidence")
    op.drop_constraint("fk_journey_current_snapshot", "journeys", type_="foreignkey")
    op.drop_index("idx_snapshots_journey_created", table_name="journey_snapshots")
    op.drop_table("journey_snapshots")
    op.drop_index("idx_journeys_status_updated", table_name="journeys")
    op.drop_index("idx_journeys_type_updated", table_name="journeys")
    op.drop_index("idx_journeys_session_updated", table_name="journeys")
    op.drop_table("journeys")
    op.drop_table("sessions")
