from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import JourneyModel, SessionModel
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.sessions import SessionRepository
from app.db.session import get_db

_serializer = URLSafeTimedSerializer(settings.SESSION_SECRET, salt="paytmflow-session")


def sign_session_id(session_id: UUID) -> str:
    """Cryptographically sign a session UUID into a secure cookie token."""
    return _serializer.dumps(str(session_id))


def unsign_session_id(token: str, max_age: int | None = None) -> UUID | None:
    """Validate token signature and return authenticated session UUID,

    or None if invalid/tampered.
    """

    try:
        raw_id = _serializer.loads(token, max_age=max_age)
        return UUID(raw_id)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def set_session_cookie(response: Response, session_id: UUID) -> None:
    """Set HttpOnly Lax signed cookie on response."""
    signed_token = sign_session_id(session_id)
    is_secure = settings.APP_ENV != "local"
    max_age_seconds = settings.SESSION_TTL_DAYS * 86400

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=signed_token,
        max_age=max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )


def resolve_session_id(request: Request) -> tuple[UUID, bool]:
    """Resolve session ID from request headers or cookie.

    Returns:
        (session_id, is_new)
    """
    # 1. CI / eval bypass header (ACCEPTED ONLY in local or ci envs)
    if settings.APP_ENV in ["local", "ci"]:
        header_val = request.headers.get("X-Session-Id")
        if header_val:
            try:
                return UUID(header_val), False
            except (ValueError, AttributeError):
                pass

    # 2. Signed Cookie
    cookie_val = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_val:
        sid = unsign_session_id(cookie_val, max_age=settings.SESSION_TTL_DAYS * 86400)
        if sid:
            return sid, False

    # 3. Mint fresh session if missing or tampered
    return uuid4(), True


async def get_current_session(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SessionModel:
    """FastAPI dependency: resolves or creates session, setting cookie when fresh."""
    session_id, is_new = resolve_session_id(request)
    session_repo = SessionRepository(db)

    sess = await session_repo.get_by_id(session_id)
    now = datetime.now(UTC)
    if not sess:
        sess = await session_repo.create(
            session_id=session_id,
            expires_at=now + timedelta(days=settings.SESSION_TTL_DAYS),
        )
        is_new = True

    # Ensure cookie is set on new sessions (or refresh if needed)
    if is_new:
        set_session_cookie(response, sess.id)

    request.state.session_created = is_new
    return sess


async def verify_journey_ownership(
    journey_id: UUID,
    current_session: SessionModel = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> JourneyModel:
    """FastAPI dependency: asserts that journey exists and is owned by current session.

    Returns 404 on both not-found and unauthorized to prevent journey ID enumeration.
    """
    journey_repo = JourneyRepository(db)
    journey = await journey_repo.get_by_id(journey_id)

    if not journey or journey.session_id != current_session.id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Journey not found or unavailable",
                    "details": {"journey_id": str(journey_id)},
                }
            },
        )

    return journey
