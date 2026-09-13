from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.models import CheckToken
from app.db.models import Base
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.schemas.enums import ActionKind, Readiness, RecommendationSource
from app.schemas.journeys import RecommendationResponse


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
async def test_get_recommendation_lending_v1(app_context: tuple[AsyncClient, async_sessionmaker]):
    client, _ = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create Lending journey
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
    snapshot_id = created_data["snapshot_id"]

    # 2. Fetch recommendation
    rec_res = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert rec_res.status_code == 200
    data = rec_res.json()

    # 3. Validate against Pydantic schema
    rec_resp = RecommendationResponse.model_validate(data)
    assert str(rec_resp.snapshot_id) == snapshot_id
    assert rec_resp.readiness == Readiness.NOT_READY
    assert rec_resp.source == RecommendationSource.AI_RANKED
    assert rec_resp.minimum_path_length == 4

    assert rec_resp.recommendation is not None
    assert rec_resp.recommendation.action_id == "SUBMIT_EMPLOYMENT_INFO"
    assert rec_resp.recommendation.kind == ActionKind.FORM
    assert "employer_name" in rec_resp.recommendation.unlocks

    # Alternatives
    alt_ids = [alt.action_id for alt in rec_resp.alternatives]
    assert "UPLOAD_INCOME_PROOF" in alt_ids
    assert "LINK_AA_ACCOUNT" in alt_ids
    assert len(rec_resp.alternatives) == 2


@pytest.mark.asyncio
async def test_get_recommendation_needs_review(app_context: tuple[AsyncClient, async_sessionmaker]):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create journey
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    journey_id = create_res.json()["journey_id"]

    # 2. Insert a snapshot with NEEDS_REVIEW
    async with session_maker() as db:
        journey_repo = JourneyRepository(db)
        snapshot_repo = SnapshotRepository(db)
        journey = await journey_repo.get_by_id(UUID(journey_id))
        assert journey is not None

        token = CheckToken(
            token_id=uuid4(),
            journey_id=journey.id,
            journey_type=journey.journey_type,
            action_id="TEST_ACTION",
            previous_snapshot_id=journey.current_snapshot_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )

        new_snapshot = await snapshot_repo.create(
            token=token,
            readiness="NEEDS_REVIEW",
            fields={
                "kyc_verified": {"status": "SATISFIED", "value": True},
                "pan_validated": {"status": "SATISFIED", "value": "ABCDE1234F"},
                "bank_account_linked": {"status": "SATISFIED", "value": "HDFC0001234"},
                "monthly_income": {"status": "BLOCKED", "value": None},
                "employment_type": {"status": "BLOCKED", "value": None},
                "employer_name": {"status": "BLOCKED", "value": None},
                "loan_offer_accepted": {"status": "BLOCKED", "value": None},
            },
            goal=journey.goal,
            pending_clarification={
                "field": "monthly_income",
                "reason": "Salary credit amount on slip differs from bank statement",
            },
        )
        await journey_repo.update_state(
            journey_id=journey.id,
            current_snapshot_id=new_snapshot.id,
            readiness="NEEDS_REVIEW",
            status="IN_PROGRESS",
        )
        await db.commit()

    # 3. Call recommendation
    rec_res = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert rec_res.status_code == 200
    data = rec_res.json()

    assert data["readiness"] == "NEEDS_REVIEW"
    assert data["recommendation"]["kind"] == "CLARIFICATION"
    assert data["recommendation"]["action_id"] == "CLARIFY_MONTHLY_INCOME"
    assert "Salary credit amount" in data["recommendation"]["why"]
    assert data["alternatives"] == []
    assert data["minimum_path_length"] == 1


@pytest.mark.asyncio
async def test_get_recommendation_ready_and_dead_end(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create journey
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    journey_id = create_res.json()["journey_id"]

    # 2. Update snapshot to READY
    async with session_maker() as db:
        journey_repo = JourneyRepository(db)
        snapshot_repo = SnapshotRepository(db)
        journey = await journey_repo.get_by_id(UUID(journey_id))
        assert journey is not None

        token_ready = CheckToken(
            token_id=uuid4(),
            journey_id=journey.id,
            journey_type=journey.journey_type,
            action_id="ACCEPT_LOAN_TERMS",
            previous_snapshot_id=journey.current_snapshot_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )

        ready_snapshot = await snapshot_repo.create(
            token=token_ready,
            readiness="READY",
            fields={
                "kyc_verified": {"status": "SATISFIED", "value": True},
                "pan_validated": {"status": "SATISFIED", "value": "ABCDE1234F"},
                "bank_account_linked": {"status": "SATISFIED", "value": "HDFC0001234"},
                "monthly_income": {"status": "SATISFIED", "value": 85000},
                "employment_type": {"status": "SATISFIED", "value": "SALARIED"},
                "employer_name": {"status": "SATISFIED", "value": "Acme Corp"},
                "loan_offer_accepted": {"status": "SATISFIED", "value": True},
            },
            goal=journey.goal,
        )
        await journey_repo.update_state(
            journey_id=journey.id,
            current_snapshot_id=ready_snapshot.id,
            readiness="READY",
            status="READY",
        )
        await db.commit()

    rec_res_ready = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert rec_res_ready.status_code == 200
    data_ready = rec_res_ready.json()
    assert data_ready["readiness"] == "READY"
    assert data_ready["recommendation"] is None
    assert data_ready["alternatives"] == []
    assert data_ready["minimum_path_length"] == 0

    # 3. Update snapshot to DEAD_END
    async with session_maker() as db:
        journey_repo = JourneyRepository(db)
        snapshot_repo = SnapshotRepository(db)
        journey = await journey_repo.get_by_id(UUID(journey_id))
        assert journey is not None

        token_dead = CheckToken(
            token_id=uuid4(),
            journey_id=journey.id,
            journey_type=journey.journey_type,
            action_id="FAIL_KYC",
            previous_snapshot_id=journey.current_snapshot_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )

        dead_end_snapshot = await snapshot_repo.create(
            token=token_dead,
            readiness="DEAD_END",
            fields={
                "kyc_verified": {"status": "FAILED", "value": False},
                "pan_validated": {"status": "SATISFIED", "value": "ABCDE1234F"},
                "bank_account_linked": {"status": "SATISFIED", "value": "HDFC0001234"},
                "monthly_income": {"status": "BLOCKED", "value": None},
                "employment_type": {"status": "BLOCKED", "value": None},
                "employer_name": {"status": "BLOCKED", "value": None},
                "loan_offer_accepted": {"status": "BLOCKED", "value": None},
            },
            goal=journey.goal,
        )
        await journey_repo.update_state(
            journey_id=journey.id,
            current_snapshot_id=dead_end_snapshot.id,
            readiness="DEAD_END",
            status="FAILED",
        )
        await db.commit()

    rec_res_dead = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert rec_res_dead.status_code == 200
    data_dead = rec_res_dead.json()
    assert data_dead["readiness"] == "DEAD_END"
    assert data_dead["recommendation"] is None
    assert data_dead["alternatives"] == []
    assert data_dead["minimum_path_length"] == 0


@pytest.mark.asyncio
async def test_get_recommendation_security_and_404(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, _ = app_context
    session_a = str(uuid4())
    session_b = str(uuid4())

    # Create journey with session A
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_res = await client.post(
        "/api/v1/journeys",
        json=payload,
        headers={"X-Session-Id": session_a},
    )
    journey_id = create_res.json()["journey_id"]

    # Access with session B -> 404
    res_b = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers={"X-Session-Id": session_b},
    )
    assert res_b.status_code == 404

    # Access non-existent journey -> 404
    fake_id = str(uuid4())
    res_fake = await client.get(
        f"/api/v1/journeys/{fake_id}/recommendation",
        headers={"X-Session-Id": session_a},
    )
    assert res_fake.status_code == 404
