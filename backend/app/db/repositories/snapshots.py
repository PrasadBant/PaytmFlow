from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import CheckToken
from app.db.models import JourneySnapshotModel


class SnapshotRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, snapshot_id: UUID) -> JourneySnapshotModel | None:
        stmt = select(JourneySnapshotModel).where(JourneySnapshotModel.id == snapshot_id)
        return await self.session.scalar(stmt)

    async def get_latest_by_journey_id(self, journey_id: UUID) -> JourneySnapshotModel | None:
        stmt = (
            select(JourneySnapshotModel)
            .where(JourneySnapshotModel.journey_id == journey_id)
            .order_by(JourneySnapshotModel.version_number.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def list_by_journey_id(self, journey_id: UUID) -> list[JourneySnapshotModel]:
        stmt = (
            select(JourneySnapshotModel)
            .where(JourneySnapshotModel.journey_id == journey_id)
            .order_by(JourneySnapshotModel.version_number.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get_by_version(
        self, journey_id: UUID, version_number: int
    ) -> JourneySnapshotModel | None:
        stmt = (
            select(JourneySnapshotModel)
            .where(
                JourneySnapshotModel.journey_id == journey_id,
                JourneySnapshotModel.version_number == version_number,
            )
        )
        return await self.session.scalar(stmt)

    async def create_initial(
        self,
        journey_id: UUID,
        readiness: str,
        fields: dict[str, Any],
        goal: dict[str, Any] | None = None,
        pending_clarification: dict[str, Any] | None = None,
        snapshot_id: UUID | None = None,
    ) -> JourneySnapshotModel:
        """Create the initial version 1 snapshot when a new journey is created."""
        snap = JourneySnapshotModel(
            id=snapshot_id or uuid4(),
            journey_id=journey_id,
            version_number=1,
            previous_snapshot_id=None,
            readiness=readiness,
            fields=fields,
            goal=goal or {},
            pending_clarification=pending_clarification,
            created_at=datetime.now(UTC),
        )
        self.session.add(snap)
        await self.session.flush()
        return snap

    async def create(
        self,
        token: CheckToken,
        readiness: str,
        fields: dict[str, Any],
        goal: dict[str, Any] | None = None,
        pending_clarification: dict[str, Any] | None = None,
        snapshot_id: UUID | None = None,
    ) -> JourneySnapshotModel:
        """Create a new snapshot for an action mutation. STRICTLY REQUIRES A CHECKTOKEN."""
        if not isinstance(token, CheckToken):
            raise TypeError(
                "Snapshot creation requires a valid CheckToken minted by deterministic_check()"
            )

        latest = await self.get_latest_by_journey_id(token.journey_id)
        if not latest:
            raise RuntimeError(f"No existing snapshot found for journey {token.journey_id}")

        if latest.id != token.previous_snapshot_id:
            raise RuntimeError(
                f"CheckToken previous_snapshot_id ({token.previous_snapshot_id}) does not match "
                f"latest journey snapshot ({latest.id})"
            )

        next_version = latest.version_number + 1

        snap = JourneySnapshotModel(
            id=snapshot_id or uuid4(),
            journey_id=token.journey_id,
            version_number=next_version,
            previous_snapshot_id=token.previous_snapshot_id,
            readiness=readiness,
            fields=fields,
            goal=goal or latest.goal,
            pending_clarification=pending_clarification,
            created_at=datetime.now(UTC),
        )
        self.session.add(snap)
        await self.session.flush()
        return snap
