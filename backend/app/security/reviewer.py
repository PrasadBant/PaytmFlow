"""Prototype-only reviewer authorization.

PaytmFlow has no real employee/staff identity system - every session is an
anonymous applicant browser session (see app/security/session.py). Rather
than pretend otherwise, this module adds the SMALLEST mechanism that keeps
the actual security boundary on the backend: a session can flip its own
`meta["role"]` via `POST /api/v1/review/role`, and every reviewer-only
endpoint depends on `verify_reviewer`, which checks that persisted
server-side session state - NEVER a frontend-supplied flag or header. A
customer cannot call a reviewer endpoint merely by navigating to `/review`
in the browser; they would first have to make their own session hit the
role-switch endpoint, which is exactly the same "prototype role switch"
the UI exposes, not a bypass of it.

This is explicitly not enterprise auth (no passwords, no distinct staff
identities, one browser session self-declares its role) and is documented
as such in the final report.
"""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SessionModel
from app.db.repositories.sessions import SessionRepository
from app.db.session import get_db
from app.schemas.enums import ErrorCode, ReviewerRole
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.security.session import get_current_session


def get_session_role(session: SessionModel) -> ReviewerRole:
    raw = (session.meta or {}).get("role", ReviewerRole.CUSTOMER.value)
    try:
        return ReviewerRole(raw)
    except ValueError:
        return ReviewerRole.CUSTOMER


async def verify_reviewer(
    current_session: SessionModel = Depends(get_current_session),
) -> SessionModel:
    """FastAPI dependency: 403s any session whose role is not REVIEW_OFFICER."""
    if get_session_role(current_session) != ReviewerRole.REVIEW_OFFICER:
        raise HTTPException(
            status_code=403,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.FORBIDDEN,
                    message="This action requires Review Center access.",
                )
            ).model_dump(mode="json"),
        )
    return current_session


def reviewer_display_name(session: SessionModel) -> str:
    """A stable, human-readable label for the reviewer - no real identity exists,
    so this is derived from the session id, prefixed for readability."""
    stored = (session.meta or {}).get("reviewer_name")
    if stored:
        return str(stored)
    return f"Reviewer-{str(session.id)[:8]}"


async def set_session_role(
    session: SessionModel,
    role: ReviewerRole,
    db: AsyncSession = Depends(get_db),
) -> SessionModel:
    repo = SessionRepository(db)
    updated = await repo.set_meta(session.id, {"role": role.value})
    await db.commit()
    return updated or session
