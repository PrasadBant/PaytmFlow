import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.seed import reset_demo_state
from app.db.session import get_db
from app.schemas.demo import DemoResetResponse

router = APIRouter()


@router.post(
    "/demo/reset",
    response_model=DemoResetResponse,
    responses={401: {"description": "Bad or missing demo secret"}},
    tags=["demo"],
    operation_id="resetDemo",
)
async def reset_demo(
    x_demo_secret: str | None = Header(None, alias="X-Demo-Secret"),
    db: AsyncSession = Depends(get_db),
):
    # Security audit hardening: constant-time comparison - a plain `!=` leaks
    # timing information proportional to the matching-prefix length, giving
    # an attacker a (slow but real) byte-by-byte oracle to brute-force this
    # destructive-reset secret. secrets.compare_digest closes that channel.
    if not x_demo_secret or not secrets.compare_digest(x_demo_secret, settings.DEMO_RESET_SECRET):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bad or missing demo secret",
        )
    elapsed_ms = await reset_demo_state(db)
    return DemoResetResponse(reset=True, elapsed_ms=elapsed_ms)
