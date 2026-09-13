from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SessionModel
from app.db.session import get_db
from app.packs.registry import pack_registry
from app.schemas.system import HealthResponse, SessionResponse
from app.security.session import get_current_session

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"], operation_id="getHealth")
async def get_health(db: AsyncSession = Depends(get_db)):
    db_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    packs_count = len(pack_registry.list_packs())
    status = "ok" if db_ok else "degraded"

    return HealthResponse(
        status=status,
        db=db_ok,
        packs_loaded=packs_count,
        packs_supported=6,
        ai_provider=settings.AI_PROVIDER,
        git_sha=settings.GIT_SHA,
    )


@router.get("/session", response_model=SessionResponse, tags=["system"], operation_id="getSession")
async def get_session(
    request: Request,
    session: SessionModel = Depends(get_current_session),
):
    created = getattr(request.state, "session_created", False)
    return SessionResponse(
        session_id=str(session.id),
        created=created,
    )
