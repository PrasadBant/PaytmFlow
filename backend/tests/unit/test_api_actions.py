from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.audit.events import AuditEventType
from app.db.models import AuditEventModel, Base
from app.db.repositories.snapshots import SnapshotRepository
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.schemas.enums import FieldStatus, JourneyStatus, Readiness
from app.schemas.journeys import ActionResponse


@pytest.fixture
async def app_context():
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
        yield client, session_maker

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_apply_action_lending_v1_to_v2_success(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create Lending journey (v1)
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    journey_id = created_data["journey_id"]
    v1_snapshot_id = created_data["snapshot_id"]

    assert created_data["version_number"] == 1
    assert created_data["progress"]["completed"] == 3
    assert created_data["progress"]["total"] == 7

    # 2. Apply action: UPLOAD_INCOME_PROOF
    idempotency_key = str(uuid4())
    action_payload = {
        "action_id": "UPLOAD_INCOME_PROOF",
        "expected_snapshot_id": v1_snapshot_id,
        "idempotency_key": idempotency_key,
        "input": {"monthly_income": 85000},
    }

    action_res = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=headers,
    )
    assert action_res.status_code == 200
    data = action_res.json()

    # 3. Validate against Pydantic model
    resp = ActionResponse.model_validate(data)

    # Journey state
    assert resp.journey.version_number == 2
    assert resp.journey.status == JourneyStatus.IN_PROGRESS
    assert resp.journey.readiness == Readiness.NOT_READY
    assert resp.journey.progress.completed == 4
    assert resp.journey.progress.pending == 3
    assert resp.journey.progress.total == 7

    income_field = next(f for f in resp.journey.fields if f.key == "monthly_income")
    assert income_field.status == FieldStatus.SATISFIED
    assert income_field.value == 85000
    assert income_field.display_value == "₹85,000"

    # Diff
    assert resp.diff.from_version == 1
    assert resp.diff.to_version == 2
    assert len(resp.diff.fields_changed) == 1
    ch = resp.diff.fields_changed[0]
    assert ch.key == "monthly_income"
    assert ch.from_status == FieldStatus.BLOCKED
    assert ch.to_status == FieldStatus.SATISFIED
    assert ch.display_value == "₹85,000"
    assert ch.cause == "ACTION:UPLOAD_INCOME_PROOF"
    assert ch.cascaded is False

    assert "UPLOAD_INCOME_PROOF" in resp.diff.actions_removed
    assert resp.diff.progress is not None
    assert resp.diff.progress.from_.completed == 3
    assert resp.diff.progress.to.completed == 4

    # Next recommendation
    assert resp.next_recommendation is not None
    assert resp.next_recommendation.snapshot_id == resp.journey.snapshot_id

    # 4. Check DB for audit events
    async with session_maker() as db:
        stmt = (
            select(AuditEventModel)
            .where(AuditEventModel.journey_id == UUID(journey_id))
            .order_by(AuditEventModel.created_at.asc())
        )
        events = list((await db.scalars(stmt)).all())
        event_types = [e.event_type for e in events]
        assert AuditEventType.JOURNEY_CREATED in event_types
        assert AuditEventType.ACTION_EXECUTED in event_types

        action_event = next(e for e in events if e.event_type == AuditEventType.ACTION_EXECUTED)
        assert action_event.payload["action_id"] == "UPLOAD_INCOME_PROOF"
        assert action_event.payload["version_number"] == 2


@pytest.mark.asyncio
async def test_apply_action_idempotency_replay(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create journey
    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    idempotency_key = str(uuid4())
    action_payload = {
        "action_id": "UPLOAD_INCOME_PROOF",
        "expected_snapshot_id": v1_snapshot_id,
        "idempotency_key": idempotency_key,
        "input": {"monthly_income": 85000},
    }

    # 2. First call -> 200
    res1 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=headers,
    )
    assert res1.status_code == 200
    data1 = res1.json()

    # 3. Second call with SAME idempotency key and same payload -> 200 (replayed)
    res2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()

    assert data1 == data2

    # 4. Verify snapshot count in DB is exactly 2 (v1 and v2, not v3)
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        snaps = await snap_repo.list_by_journey_id(UUID(journey_id))
        assert len(snaps) == 2


@pytest.mark.asyncio
async def test_apply_action_stale_returns_409(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create journey
    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    # 2. Advance to v2
    res_v2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": v1_snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 85000},
        },
        headers=headers,
    )
    assert res_v2.status_code == 200
    v2_snapshot_id = res_v2.json()["journey"]["snapshot_id"]

    # 3. Attempt another action with STALE v1 snapshot ID -> 409
    res_stale = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": v1_snapshot_id,  # STALE!
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "SALARIED"},
        },
        headers=headers,
    )
    assert res_stale.status_code == 409
    err = res_stale.json()
    assert err["error"]["code"] == "ACTION_STALE"
    assert err["error"]["current_snapshot_id"] == v2_snapshot_id
    assert err["error"]["details"]["current_snapshot_id"] == v2_snapshot_id

    # 4. Verify no new snapshot was created
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        snaps = await snap_repo.list_by_journey_id(UUID(journey_id))
        assert len(snaps) == 2


@pytest.mark.asyncio
async def test_apply_action_invalid_preconditions_returns_422(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create journey
    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    # 2. Try ACCEPT_LOAN_TERMS without monthly_income or employer_name -> 422
    res_invalid = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": v1_snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=headers,
    )
    assert res_invalid.status_code == 422
    err = res_invalid.json()
    assert err["error"]["code"] == "ACTION_INVALID"
    assert "failed_precondition" in err["error"]["details"]


@pytest.mark.asyncio
async def test_apply_action_unknown_action_returns_422(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, _ = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    res_unknown = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "NON_EXISTENT_ACTION",
            "expected_snapshot_id": v1_snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {},
        },
        headers=headers,
    )
    assert res_unknown.status_code == 422
    assert res_unknown.json()["error"]["code"] == "ACTION_INVALID"


@pytest.mark.asyncio
async def test_apply_action_validation_error_returns_400(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, _ = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    # SUBMIT_EMPLOYMENT_INFO with invalid enum option
    res_bad_val = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": v1_snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "INVALID_OPTION"},
        },
        headers=headers,
    )
    assert res_bad_val.status_code == 400
    assert res_bad_val.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_apply_action_cross_session_returns_404(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, _ = app_context
    session_a = str(uuid4())
    session_b = str(uuid4())

    create_res = await client.post(
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
    journey_id = create_res.json()["journey_id"]
    v1_snapshot_id = create_res.json()["snapshot_id"]

    res_cross = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": v1_snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 85000},
        },
        headers={"X-Session-Id": session_b},
    )
    assert res_cross.status_code == 404


@pytest.mark.asyncio
async def test_lending_golden_path_end_to_end(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    """Gate B-C Verification:

    Drives the entire Lending Golden Path through API calls from v1 to READY:
    1. POST /journeys (v1: 3/7, NOT_READY)
    2. POST /actions -> UPLOAD_INCOME_PROOF (v2: 4/7, NOT_READY)
    3. POST /actions -> SUBMIT_EMPLOYMENT_INFO (v3: 5/7, NOT_READY)
    4. POST /actions -> VERIFY_EMPLOYER_RECORD (v4: 6/7, NOT_READY)
    5. POST /actions -> ACCEPT_LOAN_TERMS (v5: 7/7, READY)
    """
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # Step 1: Create Lending Journey (v1)
    res_v1 = await client.post(
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
    assert res_v1.status_code == 201
    j_data = res_v1.json()
    journey_id = j_data["journey_id"]
    snap_id = j_data["snapshot_id"]
    assert j_data["version_number"] == 1
    assert j_data["readiness"] == "NOT_READY"
    assert j_data["status"] == "IN_PROGRESS"
    assert j_data["progress"]["completed"] == 3

    # Step 2: Upload Income Proof -> v2
    res_v2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 85000},
        },
        headers=headers,
    )
    assert res_v2.status_code == 200
    v2_data = res_v2.json()
    snap_id = v2_data["journey"]["snapshot_id"]
    assert v2_data["journey"]["version_number"] == 2
    assert v2_data["journey"]["progress"]["completed"] == 4
    assert v2_data["journey"]["readiness"] == "NOT_READY"

    # Step 3: Submit Employment Info -> v3
    res_v3 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "SALARIED"},
        },
        headers=headers,
    )
    assert res_v3.status_code == 200
    v3_data = res_v3.json()
    snap_id = v3_data["journey"]["snapshot_id"]
    assert v3_data["journey"]["version_number"] == 3
    assert v3_data["journey"]["progress"]["completed"] == 5
    assert v3_data["journey"]["readiness"] == "NOT_READY"

    # Step 4: Verify Employer Record -> v4
    res_v4 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "VERIFY_EMPLOYER_RECORD",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"employer_name": "Google LLC"},
        },
        headers=headers,
    )
    assert res_v4.status_code == 200
    v4_data = res_v4.json()
    snap_id = v4_data["journey"]["snapshot_id"]
    assert v4_data["journey"]["version_number"] == 4
    assert v4_data["journey"]["progress"]["completed"] == 6
    assert v4_data["journey"]["readiness"] == "NOT_READY"

    # Step 5: Accept Loan Terms -> v5 (Final Step: READY!)
    res_v5 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=headers,
    )
    assert res_v5.status_code == 200
    v5_data = res_v5.json()
    assert v5_data["journey"]["version_number"] == 5
    assert v5_data["journey"]["progress"]["completed"] == 7
    assert v5_data["journey"]["progress"]["pending"] == 0
    assert v5_data["journey"]["progress"]["blockers"] == 0
    assert v5_data["journey"]["readiness"] == "READY"
    assert v5_data["journey"]["status"] == "COMPLETED"
    assert v5_data["next_recommendation"]["recommendation"] is None
    assert v5_data["next_recommendation"]["readiness"] == "READY"

    # Verify Snapshot Chain in DB (exactly 5 snapshots, ordered v1..v5, no forking)
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        snaps = await snap_repo.list_by_journey_id(UUID(journey_id))
        assert len(snaps) == 5
        for i, s in enumerate(snaps, start=1):
            assert s.version_number == i
            if i > 1:
                assert s.previous_snapshot_id == snaps[i - 2].id
