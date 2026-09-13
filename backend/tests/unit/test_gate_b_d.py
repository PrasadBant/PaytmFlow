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
from app.schemas.enums import JourneyStatus, Readiness
from app.schemas.journeys import ActionResponse, JourneyStateResponse, RecommendationResponse


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
async def test_gate_b_d_full_lending_journey_with_clarification_to_ready(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    """Gate B-D Verification:

    Full Lending journey including Needs Review clarification,
    progressing through all actions and ending in READY state.
    """
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # Step 1: Create Lending Journey (v1)
    create_payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_res = await client.post("/api/v1/journeys", json=create_payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    journey_id = created_data["journey_id"]
    snap_v1_id = created_data["snapshot_id"]
    assert created_data["readiness"] == "NOT_READY"
    assert created_data["version_number"] == 1

    # Step 2: Query Recommendation
    rec_res = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert rec_res.status_code == 200
    rec_data = RecommendationResponse.model_validate(rec_res.json())
    assert rec_data.recommendation is not None
    assert rec_data.recommendation.action_id in [
        "UPLOAD_INCOME_PROOF",
        "LINK_AA_ACCOUNT",
        "SUBMIT_EMPLOYMENT_INFO",
    ]

    # Step 3: Apply Action 1 - UPLOAD_INCOME_PROOF (v1 -> v2)
    action1_res = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap_v1_id,
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 85000},
        },
        headers=headers,
    )
    assert action1_res.status_code == 200
    act1_data = ActionResponse.model_validate(action1_res.json())
    assert act1_data.journey.version_number == 2
    snap_v2_id = str(act1_data.journey.snapshot_id)

    # Step 4: Apply Action 2 - SUBMIT_EMPLOYMENT_INFO (v2 -> v3)
    action2_res = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": snap_v2_id,
            "idempotency_key": str(uuid4()),
            "input": {
                "employment_type": "SALARIED",
                "employer_name": "Acme Technologies India Pvt Ltd",
            },
        },
        headers=headers,
    )
    assert action2_res.status_code == 200
    act2_data = ActionResponse.model_validate(action2_res.json())
    assert act2_data.journey.version_number == 3
    snap_v3_id = str(act2_data.journey.snapshot_id)

    # Step 5: Ambiguity emerges on employer verification -> Transition to NEEDS_REVIEW
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        journey_repo = JourneyRepository(db)
        snap3 = await snap_repo.get_by_id(UUID(snap_v3_id))

        fields_copy = dict(snap3.fields)
        fields_copy["employer_name"] = {
            "key": "employer_name",
            "label": "Current Employer",
            "status": "AMBIGUOUS",
            "value": None,
            "display_value": None,
            "explanation": "Employer organization name could not be automatically matched",
            "resolve_action_id": "VERIFY_EMPLOYER_RECORD",
            "mandatory": True,
            "derived": False,
            "display": True,
            "ambiguity": {
                "ambiguity_id": "EMPLOYER_UNVERIFIED",
                "field": "employer_name",
                "reason": "Employer organization name could not be matched",
                "question": "Please confirm the registered corporate name of your employer",
                "answer_type": "TEXT",
            },
        }

        token = CheckToken(
            token_id=uuid4(),
            journey_id=UUID(journey_id),
            journey_type="LENDING",
            action_id="EVIDENCE_AMBIGUITY_FLAGGED",
            previous_snapshot_id=UUID(snap_v3_id),
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )
        amb_snap = await snap_repo.create(
            token=token,
            readiness="NEEDS_REVIEW",
            fields=fields_copy,
            goal=snap3.goal,
            pending_clarification={
                "ambiguity_id": "EMPLOYER_UNVERIFIED",
                "field": "employer_name",
                "reason": "Employer organization name could not be matched",
                "question": "Please confirm the registered corporate name of your employer",
                "answer_type": "TEXT",
            },
        )
        await journey_repo.update_state(
            journey_id=UUID(journey_id),
            current_snapshot_id=amb_snap.id,
            readiness="NEEDS_REVIEW",
            status="IN_PROGRESS",
        )
        await db.commit()
        snap_amb_id = str(amb_snap.id)

    # Verify Journey State is in NEEDS_REVIEW
    state_res = await client.get(f"/api/v1/journeys/{journey_id}", headers=headers)
    assert state_res.status_code == 200
    state_data = JourneyStateResponse.model_validate(state_res.json())
    assert state_data.readiness == Readiness.NEEDS_REVIEW
    assert state_data.pending_clarification is not None
    assert state_data.pending_clarification.ambiguity is not None
    assert state_data.pending_clarification.ambiguity.ambiguity_id == "EMPLOYER_UNVERIFIED"

    # Step 6: Submit Clarification to resolve ambiguity (v4 -> v5)
    clarify_res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "EMPLOYER_UNVERIFIED",
            "field": "employer_name",
            "answer": "Acme Technologies India Private Limited",
            "expected_snapshot_id": snap_amb_id,
        },
        headers=headers,
    )
    assert clarify_res.status_code == 200
    clarify_data = ActionResponse.model_validate(clarify_res.json())
    assert clarify_data.journey.readiness == Readiness.NOT_READY
    assert clarify_data.journey.pending_clarification is None
    snap_v5_id = str(clarify_data.journey.snapshot_id)

    # Step 7: Final Action - ACCEPT_LOAN_TERMS (v5 -> v6)
    action3_res = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": snap_v5_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=headers,
    )
    assert action3_res.status_code == 200
    final_act_data = ActionResponse.model_validate(action3_res.json())

    # Step 8: Gate B-D Verified: Readiness is READY, Status is COMPLETED
    assert final_act_data.journey.readiness == Readiness.READY
    assert final_act_data.journey.status == JourneyStatus.COMPLETED
    assert final_act_data.journey.progress.completed == final_act_data.journey.progress.total
    assert final_act_data.diff.readiness is not None
    assert final_act_data.diff.readiness.to == Readiness.READY
