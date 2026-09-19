from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReviewCaseModel


class ReviewCaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, case_id: UUID) -> ReviewCaseModel | None:
        stmt = select(ReviewCaseModel).where(ReviewCaseModel.id == case_id)
        return await self.session.scalar(stmt)

    async def get_by_id_for_update(self, case_id: UUID) -> ReviewCaseModel | None:
        """Row lock the case for atomic claim/resolve/escalate transitions."""
        stmt = select(ReviewCaseModel).where(ReviewCaseModel.id == case_id).with_for_update()
        return await self.session.scalar(stmt)

    async def find_open_by_dedupe_key(
        self, journey_id: UUID, dedupe_key: str
    ) -> ReviewCaseModel | None:
        stmt = select(ReviewCaseModel).where(
            ReviewCaseModel.journey_id == journey_id,
            ReviewCaseModel.dedupe_key == dedupe_key,
        )
        return await self.session.scalar(stmt)

    async def find_open_by_base_key(
        self, journey_id: UUID, base_key: str
    ) -> ReviewCaseModel | None:
        """Like `find_open_by_dedupe_key`, but matches any attempt-numbered
        variant of `base_key` (see ReviewCaseService.create_or_get_open_case)
        and only ever returns a case that is still actionable (not RESOLVED/
        CANCELLED) - a terminal case never blocks a later, genuinely new
        occurrence of the same ambiguity from getting its own case."""
        stmt = select(ReviewCaseModel).where(
            ReviewCaseModel.journey_id == journey_id,
            ReviewCaseModel.dedupe_key.like(f"{base_key}:%"),
            ReviewCaseModel.status.not_in(["RESOLVED", "CANCELLED"]),
        )
        return await self.session.scalar(stmt)

    async def count_by_base_key(self, journey_id: UUID, base_key: str) -> int:
        stmt = select(func.count(ReviewCaseModel.id)).where(
            ReviewCaseModel.journey_id == journey_id,
            ReviewCaseModel.dedupe_key.like(f"{base_key}:%"),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_by_journey(self, journey_id: UUID) -> list[ReviewCaseModel]:
        stmt = (
            select(ReviewCaseModel)
            .where(ReviewCaseModel.journey_id == journey_id)
            .order_by(ReviewCaseModel.created_at.desc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def list_queue(
        self,
        status: str | None = None,
        priority: str | None = None,
        journey_type: str | None = None,
        assigned_reviewer: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ReviewCaseModel]:
        from app.db.models import JourneyModel

        stmt = select(ReviewCaseModel)
        if status:
            stmt = stmt.where(ReviewCaseModel.status == status)
        if priority:
            stmt = stmt.where(ReviewCaseModel.priority == priority)
        if assigned_reviewer:
            stmt = stmt.where(ReviewCaseModel.assigned_reviewer == assigned_reviewer)
        if journey_type:
            stmt = stmt.join(JourneyModel, JourneyModel.id == ReviewCaseModel.journey_id).where(
                JourneyModel.journey_type == journey_type
            )
        stmt = stmt.order_by(ReviewCaseModel.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(ReviewCaseModel.status, func.count(ReviewCaseModel.id)).group_by(
            ReviewCaseModel.status
        )
        result = await self.session.execute(stmt)
        return dict(result.all())

    async def count_resolved_today(self) -> int:
        now = datetime.now(UTC)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(ReviewCaseModel.id)).where(
            ReviewCaseModel.status == "RESOLVED",
            ReviewCaseModel.resolved_at.is_not(None),
            ReviewCaseModel.resolved_at >= start_of_day,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def _next_case_seq(self) -> int:
        stmt = select(func.coalesce(func.max(ReviewCaseModel.case_seq), 0) + 1)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def create(
        self,
        journey_id: UUID,
        session_id: UUID | None,
        dedupe_key: str,
        field_key: str,
        reason_code: str,
        reason_title: str,
        reason_description: str,
        context_snapshot_id: UUID | None,
        priority: str = "MEDIUM",
        case_id: UUID | None = None,
    ) -> ReviewCaseModel:
        now = datetime.now(UTC)
        case = ReviewCaseModel(
            id=case_id or uuid4(),
            case_seq=await self._next_case_seq(),
            journey_id=journey_id,
            session_id=session_id,
            dedupe_key=dedupe_key,
            field_key=field_key,
            context_snapshot_id=context_snapshot_id,
            reason_code=reason_code,
            reason_title=reason_title,
            reason_description=reason_description,
            priority=priority,
            status="REVIEW_REQUIRED",
            case_version=1,
            created_at=now,
            updated_at=now,
        )
        self.session.add(case)
        await self.session.flush()
        return case

    async def save(self, case: ReviewCaseModel, **updates: Any) -> ReviewCaseModel:
        for key, value in updates.items():
            setattr(case, key, value)
        case.updated_at = datetime.now(UTC)
        await self.session.flush()
        return case
