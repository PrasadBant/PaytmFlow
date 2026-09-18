from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import JourneyModel


class JourneyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        journey_id: UUID,
        load_snapshots: bool = False,
    ) -> JourneyModel | None:
        stmt = select(JourneyModel).where(JourneyModel.id == journey_id)
        if load_snapshots:
            stmt = stmt.options(selectinload(JourneyModel.snapshots))
        return await self.session.scalar(stmt)

    async def get_by_id_for_update(
        self,
        journey_id: UUID,
    ) -> JourneyModel | None:
        """Row lock journey record for atomic mutation (SELECT ... FOR UPDATE)."""
        stmt = select(JourneyModel).where(JourneyModel.id == journey_id).with_for_update()
        return await self.session.scalar(stmt)

    async def list_by_session(
        self,
        session_id: UUID,
        status: str | None = None,
        journey_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JourneyModel]:
        stmt = select(JourneyModel).where(JourneyModel.session_id == session_id)
        if status:
            stmt = stmt.where(JourneyModel.status == status)
        if journey_type:
            stmt = stmt.where(JourneyModel.journey_type == journey_type)
        stmt = stmt.order_by(JourneyModel.updated_at.desc()).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(
        self,
        session_id: UUID,
        journey_type: str,
        schema_version: str = "1.0.0",
        status: str = "IN_PROGRESS",
        readiness: str = "NOT_READY",
        goal: dict[str, Any] | None = None,
        natural_language: str | None = None,
        display_title: str = "",
        display_summary: str = "",
        current_snapshot_id: UUID | None = None,
        journey_id: UUID | None = None,
    ) -> JourneyModel:
        now = datetime.now(UTC)
        journey = JourneyModel(
            id=journey_id or uuid4(),
            session_id=session_id,
            journey_type=journey_type,
            schema_version=schema_version,
            status=status,
            readiness=readiness,
            current_snapshot_id=current_snapshot_id,
            goal=goal or {},
            natural_language=natural_language,
            display_title=display_title,
            display_summary=display_summary,
            created_at=now,
            updated_at=now,
        )
        self.session.add(journey)
        await self.session.flush()
        return journey

    async def update_state(
        self,
        journey_id: UUID,
        current_snapshot_id: UUID,
        readiness: str,
        status: str,
        updated_at: datetime | None = None,
    ) -> JourneyModel | None:
        journey = await self.get_by_id(journey_id)
        if not journey:
            return None

        journey.current_snapshot_id = current_snapshot_id
        journey.readiness = readiness
        journey.status = status
        journey.updated_at = updated_at or datetime.now(UTC)
        await self.session.flush()
        return journey
