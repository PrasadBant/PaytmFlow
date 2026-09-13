from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import IdempotencyKeyModel


class IdempotencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> IdempotencyKeyModel | None:
        stmt = select(IdempotencyKeyModel).where(IdempotencyKeyModel.key == key)
        return await self.session.scalar(stmt)

    async def create(
        self,
        key: str,
        session_id: UUID,
        journey_id: UUID,
        action_id: str,
        request_hash: str,
        response_body: dict[str, Any],
        status_code: int = 200,
    ) -> IdempotencyKeyModel:
        record = IdempotencyKeyModel(
            key=key,
            session_id=session_id,
            journey_id=journey_id,
            action_id=action_id,
            request_hash=request_hash,
            response_body=response_body,
            status_code=status_code,
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record
