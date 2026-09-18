"""Add missing journeys.natural_language column

The JourneyModel ORM has carried `natural_language: Mapped[str | None]`
since before this repo's Alembic history starts, but no migration ever
created the column - INSERT into journeys 500s with UndefinedColumn.

Revision ID: 003_journey_natural_language
Revises: 002_evidence_verification_result
Create Date: 2026-09-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_journey_natural_language"
down_revision: str | None = "002_evidence_verification_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("journeys", sa.Column("natural_language", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("journeys", "natural_language")
