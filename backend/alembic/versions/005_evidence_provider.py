"""Persist which AIProvider produced each evidence extraction

Sarvam AI integration, provider metadata / source traceability: records
"sarvam" / "local_ml" / "llm" / "mock" on each evidence row so the Review
Center can show reviewers a real "Source: Sarvam Vision" label instead of
an opaque confidence number. Nullable/backfill-free: existing rows simply
have no recorded provider, which the API layer treats as "unknown source"
rather than guessing.

Revision ID: 005_evidence_provider
Revises: 004_review_cases
Create Date: 2026-09-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_evidence_provider"
down_revision: str | None = "004_review_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("provider", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("evidence", "provider")
