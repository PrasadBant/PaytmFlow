from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEventModel


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_journey_id(self, journey_id: UUID) -> list[AuditEventModel]:
        stmt = (
            select(AuditEventModel)
            .where(AuditEventModel.journey_id == journey_id)
            .order_by(AuditEventModel.created_at.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(
        self,
        journey_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        session_id: UUID | None = None,
        event_id: UUID | None = None,
    ) -> AuditEventModel:
        event = AuditEventModel(
            id=event_id or uuid4(),
            journey_id=journey_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.flush()
        return event
