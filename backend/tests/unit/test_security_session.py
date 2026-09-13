from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.sessions import SessionRepository
from app.db.session import create_immutability_triggers
from app.security.session import (
    get_current_session,
    resolve_session_id,
    set_session_cookie,
    sign_session_id,
    unsign_session_id,
    verify_journey_ownership,
)


@pytest.fixture
async def db_session() -> AsyncSession:
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session

    await test_engine.dispose()


def test_session_signing_and_unsigning():
    test_id = uuid4()
    signed = sign_session_id(test_id)
    assert isinstance(signed, str)
    assert len(signed) > 20

    # Valid unsign
    recovered = unsign_session_id(signed)
    assert recovered == test_id

    # Tampered signature
    tampered = signed + "tamper"
    assert unsign_session_id(tampered) is None

    # Corrupted / random string
    assert unsign_session_id("invalid-not-a-token") is None
    assert unsign_session_id("") is None


def test_x_session_id_bypass_gated_to_local_and_ci(monkeypatch):
    test_id = uuid4()
    req = MagicMock()
    req.headers = {"X-Session-Id": str(test_id)}
    req.cookies = {}

    # 1. In local environment -> accepted
    monkeypatch.setattr(settings, "APP_ENV", "local")
    resolved_id, is_new = resolve_session_id(req)
    assert resolved_id == test_id
    assert is_new is False

    # 2. In ci environment -> accepted
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    resolved_id, is_new = resolve_session_id(req)
    assert resolved_id == test_id
    assert is_new is False

    # 3. In demo environment -> STRICTLY IGNORED
    monkeypatch.setattr(settings, "APP_ENV", "demo")
    resolved_id, is_new = resolve_session_id(req)
    assert resolved_id != test_id
    assert is_new is True


def test_cookie_resolution_and_fallback(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "demo")
    test_id = uuid4()
    signed_token = sign_session_id(test_id)

    # Valid cookie
    req_valid = MagicMock()
    req_valid.headers = {}
    req_valid.cookies = {settings.SESSION_COOKIE_NAME: signed_token}

    resolved_id, is_new = resolve_session_id(req_valid)
    assert resolved_id == test_id
    assert is_new is False

    # Tampered cookie -> fallback to fresh session
    req_tampered = MagicMock()
    req_tampered.headers = {}
    req_tampered.cookies = {settings.SESSION_COOKIE_NAME: "tampered_token_value"}

    resolved_id2, is_new2 = resolve_session_id(req_tampered)
    assert resolved_id2 != test_id
    assert is_new2 is True


def test_set_session_cookie(monkeypatch):
    test_id = uuid4()
    response = MagicMock()

    # In local -> secure=False
    monkeypatch.setattr(settings, "APP_ENV", "local")
    set_session_cookie(response, test_id)
    response.set_cookie.assert_called_with(
        key=settings.SESSION_COOKIE_NAME,
        value=response.set_cookie.call_args[1]["value"],
        max_age=settings.SESSION_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )

    # In demo/production -> secure=True
    monkeypatch.setattr(settings, "APP_ENV", "demo")
    set_session_cookie(response, test_id)
    assert response.set_cookie.call_args[1]["secure"] is True


async def test_get_current_session_dependency(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "local")
    test_id = uuid4()
    req = MagicMock()
    req.headers = {"X-Session-Id": str(test_id)}
    req.cookies = {}
    res = MagicMock()

    # First call creates session in DB
    session_model = await get_current_session(request=req, response=res, db=db_session)
    assert session_model.id == test_id

    # Second call returns existing session
    session_model_2 = await get_current_session(request=req, response=res, db=db_session)
    assert session_model_2.id == test_id


async def test_verify_journey_ownership_enforcement(db_session: AsyncSession):
    session_repo = SessionRepository(db_session)
    journey_repo = JourneyRepository(db_session)

    now = datetime.now(UTC)
    sess_a = await session_repo.create(expires_at=now + timedelta(days=30))
    sess_b = await session_repo.create(expires_at=now + timedelta(days=30))

    journey_a = await journey_repo.create(session_id=sess_a.id, journey_type="LENDING")

    # 1. Owner accesses journey -> Success
    owned = await verify_journey_ownership(
        journey_id=journey_a.id,
        current_session=sess_a,
        db=db_session,
    )
    assert owned.id == journey_a.id

    # 2. Non-owner (sess_b) accesses journey -> 404 NOT_FOUND (never 403)
    with pytest.raises(HTTPException) as exc_info:
        await verify_journey_ownership(
            journey_id=journey_a.id,
            current_session=sess_b,
            db=db_session,
        )
    assert exc_info.value.status_code == 404

    # 3. Non-existent journey -> 404 NOT_FOUND
    with pytest.raises(HTTPException) as exc_info:
        await verify_journey_ownership(
            journey_id=uuid4(),
            current_session=sess_a,
            db=db_session,
        )
    assert exc_info.value.status_code == 404
