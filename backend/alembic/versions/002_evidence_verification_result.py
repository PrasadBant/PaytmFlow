"""Persist the real, server-computed evidence verification result

Document AI integration integrity fix: `evidence.verified` (the SAME
`is_verified` decision already computed at upload time in
EvidenceReconciliationService.submit_evidence - AI-verified AND
confidence >= manifest threshold AND no conflicts) and `evidence.
raw_values` (the AI's real, validated target-field values) are now
persisted so a LATER action-execution request can consume the actual
result instead of ever falling back to a simulated/default value.

Revision ID: 002_evidence_verification_result
Revises: 001_initial_schema
Create Date: 2026-09-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002_evidence_verification_result"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("evidence", sa.Column("raw_values", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "raw_values")
    op.drop_column("evidence", "verified")
