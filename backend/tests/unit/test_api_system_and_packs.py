import json
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.schemas.enums import JourneyType
from app.schemas.packs import JourneyPackDetail, JourneyPacksListResponse
from app.schemas.system import HealthResponse, SessionResponse

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "contract" / "fixtures"


@pytest.fixture
async def client_with_db():
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_immutability_triggers(conn)

    session_maker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_health_endpoint(client_with_db: AsyncClient):
    response = await client_with_db.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()

    # Validates schema
    health = HealthResponse.model_validate(data)
    assert health.status == "ok"
    assert health.db is True
    assert health.packs_loaded == 6
    assert health.packs_supported == 6
    assert health.ai_provider in ["mock", "llm", "local_ml"]


@pytest.mark.asyncio
async def test_session_endpoint_lifecycle(client_with_db: AsyncClient):
    # 1. First anonymous request -> newly created
    res1 = await client_with_db.get("/api/v1/session")
    assert res1.status_code == 200
    data1 = res1.json()

    sess1 = SessionResponse.model_validate(data1)
    assert sess1.created is True
    assert UUID(sess1.session_id)  # valid UUID

    # Must set pf_session cookie
    cookies = res1.cookies
    assert "pf_session" in cookies
    cookie_token = cookies["pf_session"]

    # 2. Subsequent request with the cookie -> existing session, created=False
    client_with_db.cookies.set("pf_session", cookie_token)
    res2 = await client_with_db.get("/api/v1/session")
    assert res2.status_code == 200
    data2 = res2.json()

    sess2 = SessionResponse.model_validate(data2)
    assert sess2.created is False
    assert sess2.session_id == sess1.session_id


@pytest.mark.asyncio
async def test_session_endpoint_x_session_bypass(client_with_db: AsyncClient):
    fixed_id = "11111111-2222-3333-4444-555555555555"
    res = await client_with_db.get(
        "/api/v1/session",
        headers={"X-Session-Id": fixed_id},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == fixed_id


@pytest.mark.asyncio
async def test_list_journey_packs_matches_fixture(client_with_db: AsyncClient):
    response = await client_with_db.get("/api/v1/journey-packs")
    assert response.status_code == 200
    data = response.json()

    # Validate against Pydantic schema
    parsed = JourneyPacksListResponse.model_validate(data)
    assert len(parsed.packs) == 6

    # Verify against committed fixture
    fixture_path = FIXTURES_DIR / "packs.list.json"
    assert fixture_path.exists(), f"Missing fixture at {fixture_path}"
    with open(fixture_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert len(data["packs"]) == len(expected["packs"])
    for actual_pack, exp_pack in zip(data["packs"], expected["packs"], strict=True):
        assert actual_pack["journey_type"] == exp_pack["journey_type"]
        assert actual_pack["display_name"] == exp_pack["display_name"]
        assert actual_pack["description"] == exp_pack["description"]
        assert actual_pack["icon"] == exp_pack["icon"]
        assert actual_pack["flagship_demo"] == exp_pack["flagship_demo"]
        assert actual_pack["lifecycle_status"] == exp_pack["lifecycle_status"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "journey_type",
    [
        JourneyType.LENDING,
        JourneyType.INSURANCE,
        JourneyType.CREDIT_CARD,
        JourneyType.KYC,
        JourneyType.ACCOUNT_OPENING,
        JourneyType.INVESTMENT,
    ],
)
async def test_get_journey_pack_detail_matches_fixture(
    client_with_db: AsyncClient,
    journey_type: JourneyType,
):
    response = await client_with_db.get(f"/api/v1/journey-packs/{journey_type.value}")
    assert response.status_code == 200
    data = response.json()

    # Validate against schema
    JourneyPackDetail.model_validate(data)

    # Validate against fixture
    fixture_path = FIXTURES_DIR / f"packs.{journey_type.value}.json"
    assert fixture_path.exists(), f"Missing fixture {fixture_path}"
    with open(fixture_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert data["journey_type"] == expected["journey_type"]
    assert data["display_name"] == expected["display_name"]
    assert data["description"] == expected["description"]
    assert data["icon"] == expected["icon"]
    assert data["flagship_demo"] == expected["flagship_demo"]
    assert data["lifecycle_status"] == expected["lifecycle_status"]
    assert data["schema_version"] == expected["schema_version"]
    assert data["supports_natural_language"] == expected["supports_natural_language"]
    assert data["ui_labels"] == expected["ui_labels"]

    # Verify goal schema fields
    assert len(data["goal_schema"]) == len(expected["goal_schema"])
    for actual_field, exp_field in zip(data["goal_schema"], expected["goal_schema"], strict=True):
        assert actual_field["key"] == exp_field["key"]
        assert actual_field["type"] == exp_field["type"]
        assert actual_field["label"] == exp_field["label"]
        assert actual_field["required"] == exp_field["required"]
        if "options" in exp_field and exp_field["options"] is not None:
            assert len(actual_field["options"]) == len(exp_field["options"])


@pytest.mark.asyncio
async def test_get_journey_pack_invalid_type(client_with_db: AsyncClient):
    response = await client_with_db.get("/api/v1/journey-packs/UNKNOWN_TYPE")
    assert response.status_code in [400, 404, 422]
