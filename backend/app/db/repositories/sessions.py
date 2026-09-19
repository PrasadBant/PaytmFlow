from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SessionModel


class SessionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, session_id: UUID) -> SessionModel | None:
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        return await self.session.scalar(stmt)

    async def create(
        self,
        expires_at: datetime,
        meta: dict[str, Any] | None = None,
        session_id: UUID | None = None,
    ) -> SessionModel:
        sess = SessionModel(
            id=session_id or uuid4(),
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            meta=meta or {},
        )
        self.session.add(sess)
        await self.session.flush()
        return sess

    async def set_meta(
        self,
        session_id: UUID,
        meta_updates: dict[str, Any],
    ) -> SessionModel | None:
        sess = await self.get_by_id(session_id)
        if not sess:
            return None
        sess.meta = {**(sess.meta or {}), **meta_updates}
        await self.session.flush()
        return sess

    async def touch(
        self,
        session_id: UUID,
        new_expires_at: datetime,
    ) -> SessionModel | None:
        sess = await self.get_by_id(session_id)
        if not sess:
            return None
        sess.expires_at = new_expires_at
        await self.session.flush()
        return sess
