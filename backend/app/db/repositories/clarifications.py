from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClarificationModel


class ClarificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, clarification_id: UUID) -> ClarificationModel | None:
        stmt = select(ClarificationModel).where(ClarificationModel.id == clarification_id)
        return await self.session.scalar(stmt)

    async def get_pending_by_journey_id(self, journey_id: UUID) -> ClarificationModel | None:
        stmt = (
            select(ClarificationModel)
            .where(
                ClarificationModel.journey_id == journey_id,
                ClarificationModel.resolved_at.is_(None),
            )
            .order_by(ClarificationModel.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def list_by_journey_id(self, journey_id: UUID) -> list[ClarificationModel]:
        stmt = (
            select(ClarificationModel)
            .where(ClarificationModel.journey_id == journey_id)
            .order_by(ClarificationModel.created_at.asc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(
        self,
        journey_id: UUID,
        ambiguity_id: str,
        field_key: str,
        question: str,
        answer_type: str,
        clarification_id: UUID | None = None,
    ) -> ClarificationModel:
        clarification = ClarificationModel(
            id=clarification_id or uuid4(),
            journey_id=journey_id,
            ambiguity_id=ambiguity_id,
            field_key=field_key,
            question=question,
            answer_type=answer_type,
            user_response=None,
            resolved_at=None,
            created_at=datetime.now(UTC),
        )
        self.session.add(clarification)
        await self.session.flush()
        return clarification

    async def resolve(
        self,
        clarification_id: UUID,
        user_response: dict[str, Any],
    ) -> ClarificationModel | None:
        clarification = await self.get_by_id(clarification_id)
        if not clarification:
            return None

        clarification.user_response = user_response
        clarification.resolved_at = datetime.now(UTC)
        await self.session.flush()
        return clarification
