import json
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.schemas.enums import JourneyStatus, JourneyType, Readiness, ResumeScreen
from app.schemas.journeys import JourneyStateResponse

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
async def test_create_lending_journey_matches_fixture(client_with_db: AsyncClient):
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }

    response = await client_with_db.post("/api/v1/journeys", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    # 1. Pydantic validation
    state = JourneyStateResponse.model_validate(data)
    assert state.journey_type == JourneyType.LENDING
    assert state.schema_version == "1.0.0"
    assert state.version_number == 1
    assert state.readiness == Readiness.NOT_READY
    assert state.status == JourneyStatus.IN_PROGRESS

    # 2. Progress counts: 3 completed, 4 pending, 3 blockers, 7 total
    assert state.progress.completed == 3
    assert state.progress.pending == 4
    assert state.progress.blockers == 3
    assert state.progress.total == 7

    # 3. Display info
    assert state.display.title == "Personal Loan"
    assert state.display.summary == "₹2,00,000 · Home Renovation"

    # 4. Compare against v1.state.json fixture
    fixture_path = FIXTURES_DIR / "lending" / "v1.state.json"
    with open(fixture_path, encoding="utf-8") as f:
        expected = json.load(f)

    assert len(data["fields"]) == len(expected["fields"])
    for actual_f, exp_f in zip(data["fields"], expected["fields"], strict=True):
        assert actual_f["key"] == exp_f["key"]
        assert actual_f["label"] == exp_f["label"]
        assert actual_f["status"] == exp_f["status"]
        assert actual_f["value"] == exp_f["value"]
        assert actual_f["display_value"] == exp_f["display_value"]
        assert actual_f["mandatory"] == exp_f["mandatory"]
        if "explanation" in exp_f and exp_f["explanation"]:
            assert actual_f["explanation"] == exp_f["explanation"]
        if "resolve_action_id" in exp_f and exp_f["resolve_action_id"]:
            assert actual_f["resolve_action_id"] == exp_f["resolve_action_id"]


@pytest.mark.asyncio
async def test_create_journey_validation_errors(client_with_db: AsyncClient):
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # Missing required field
    res1 = await client_with_db.post(
        "/api/v1/journeys",
        json={"journey_type": "LENDING", "goal": {"loan_purpose": "HOME_RENOVATION"}},
        headers=headers,
    )
    assert res1.status_code == 400
    err1 = res1.json()
    assert err1["error"]["code"] == "VALIDATION_ERROR"
    assert "loan_amount" in err1["error"]["details"]

    # Value out of bounds (< min 50000)
    res2 = await client_with_db.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 1000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
            },
        },
        headers=headers,
    )
    assert res2.status_code == 400
    err2 = res2.json()
    assert err2["error"]["code"] == "VALIDATION_ERROR"
    assert "loan_amount" in err2["error"]["details"]

    # Unknown goal field
    res3 = await client_with_db.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 200000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
                "unauthorized_field": "hacked",
            },
        },
        headers=headers,
    )
    assert res3.status_code == 400
    err3 = res3.json()
    assert err3["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_journey_by_id_and_cross_session_security(client_with_db: AsyncClient):
    session_a = str(uuid4())
    session_b = str(uuid4())

    # 1. Create with Session A
    create_res = await client_with_db.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 200000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
            },
        },
        headers={"X-Session-Id": session_a},
    )
    assert create_res.status_code == 201
    journey_id = create_res.json()["journey_id"]

    # 2. Fetch with same session A -> 200
    get_res_a = await client_with_db.get(
        f"/api/v1/journeys/{journey_id}",
        headers={"X-Session-Id": session_a},
    )
    assert get_res_a.status_code == 200
    assert get_res_a.json()["journey_id"] == journey_id

    # 3. Fetch with different session B -> 404
    get_res_b = await client_with_db.get(
        f"/api/v1/journeys/{journey_id}",
        headers={"X-Session-Id": session_b},
    )
    assert get_res_b.status_code == 404

    # 4. Fetch non-existent ID -> 404
    non_existent = str(uuid4())
    get_res_none = await client_with_db.get(
        f"/api/v1/journeys/{non_existent}",
        headers={"X-Session-Id": session_a},
    )
    assert get_res_none.status_code == 404


@pytest.mark.asyncio
async def test_list_journeys_flow_and_filtering(client_with_db: AsyncClient):
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # Empty initially
    res_empty = await client_with_db.get("/api/v1/journeys", headers=headers)
    assert res_empty.status_code == 200
    assert res_empty.json()["journeys"] == []

    # Create 1 Lending journey
    await client_with_db.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 200000,
                "loan_purpose": "HOME_RENOVATION",
                "tenure_months": 24,
            },
        },
        headers=headers,
    )

    # Create 1 Insurance journey
    await client_with_db.post(
        "/api/v1/journeys",
        json={
            "journey_type": "INSURANCE",
            "goal": {
                "sum_insured": 500000,
                "policy_type": "INDIVIDUAL",
            },
        },
        headers=headers,
    )

    # List all
    res_all = await client_with_db.get("/api/v1/journeys", headers=headers)
    assert res_all.status_code == 200
    all_items = res_all.json()["journeys"]
    assert len(all_items) == 2

    # Check first item (newest = Insurance)
    assert all_items[0]["journey_type"] == "INSURANCE"
    assert all_items[0]["display_name"] == "Health Insurance"
    assert all_items[0]["summary"] == "₹5,00,000 · Individual Cover"
    assert all_items[0]["resume_screen"] == ResumeScreen.STATUS

    # Check second item (Lending)
    assert all_items[1]["journey_type"] == "LENDING"
    assert all_items[1]["display_name"] == "Personal Loan"
    assert all_items[1]["summary"] == "₹2,00,000 · Home Renovation"
    assert all_items[1]["progress"]["completed"] == 3
    assert all_items[1]["progress"]["total"] == 7
    assert all_items[1]["resume_screen"] == ResumeScreen.STATUS

    # Filter by journey_type=LENDING
    res_lending = await client_with_db.get(
        "/api/v1/journeys",
        params={"journey_type": "LENDING"},
        headers=headers,
    )
    assert res_lending.status_code == 200
    lending_items = res_lending.json()["journeys"]
    assert len(lending_items) == 1
    assert lending_items[0]["journey_type"] == "LENDING"

    # Filter by non-existent status
    res_completed = await client_with_db.get(
        "/api/v1/journeys",
        params={"status": "COMPLETED"},
        headers=headers,
    )
    assert res_completed.status_code == 200
    assert len(res_completed.json()["journeys"]) == 0
