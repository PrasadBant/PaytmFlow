from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.audit.events import AuditEventType
from app.core.models import CheckToken
from app.db.models import AuditEventModel, Base
from app.db.repositories.clarifications import ClarificationRepository
from app.db.repositories.journeys import JourneyRepository
from app.db.repositories.snapshots import SnapshotRepository
from app.db.session import create_immutability_triggers, get_db
from app.main import app
from app.schemas.enums import FieldStatus, Readiness
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
async def test_submit_clarification_single_ambiguity_success(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create a Lending journey
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
    initial_snap_id = UUID(created_data["snapshot_id"])

    # 2. Setup an ambiguous state for monthly_income
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        journey_repo = JourneyRepository(db)
        snap = await snap_repo.get_by_id(initial_snap_id)

        fields_copy = dict(snap.fields)
        fields_copy["monthly_income"] = {
            "key": "monthly_income",
            "label": "Monthly Income",
            "status": "AMBIGUOUS",
            "value": None,
            "display_value": None,
            "explanation": "Ambiguity detected in income proof",
            "resolve_action_id": "UPLOAD_INCOME_PROOF",
            "mandatory": True,
            "derived": False,
            "display": True,
            "ambiguity": {
                "ambiguity_id": "INCOME_MISMATCH",
                "field": "monthly_income",
                "reason": "Bank statement credit differs from salary slip",
                "question": "Which monthly income figure should be used for assessment?",
                "answer_type": "MONEY",
                "choices": None,
            },
        }
        token = CheckToken(
            token_id=uuid4(),
            journey_id=UUID(journey_id),
            journey_type="LENDING",
            action_id="TEST_SETUP",
            previous_snapshot_id=initial_snap_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )
        ambiguous_snap = await snap_repo.create(
            token=token,
            readiness="NEEDS_REVIEW",
            fields=fields_copy,
            goal=snap.goal,
            pending_clarification={
                "ambiguity_id": "INCOME_MISMATCH",
                "field": "monthly_income",
                "reason": "Bank statement credit differs from salary slip",
                "question": "Which monthly income figure should be used for assessment?",
                "answer_type": "MONEY",
            },
        )
        await journey_repo.update_state(
            journey_id=UUID(journey_id),
            current_snapshot_id=ambiguous_snap.id,
            readiness="NEEDS_REVIEW",
            status="IN_PROGRESS",
        )
        await db.commit()
        current_snap_id = str(ambiguous_snap.id)

    # 3. Submit clarification
    clarify_payload = {
        "ambiguity_id": "INCOME_MISMATCH",
        "field": "monthly_income",
        "answer": 95000,
        "expected_snapshot_id": current_snap_id,
    }

    res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json=clarify_payload,
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()

    # Validate schema
    resp_obj = ActionResponse.model_validate(data)
    assert resp_obj.journey.version_number == 3
    assert resp_obj.journey.readiness == Readiness.NOT_READY
    assert resp_obj.journey.pending_clarification is None

    # Check field was updated to SATISFIED
    income_f = next(f for f in resp_obj.journey.fields if f.key == "monthly_income")
    assert income_f.status == FieldStatus.SATISFIED
    assert income_f.value == 95000
    assert income_f.display_value == "₹95,000"

    # Check diff
    assert resp_obj.diff.from_version == 2
    assert resp_obj.diff.to_version == 3
    assert len(resp_obj.diff.fields_changed) == 1
    ch = resp_obj.diff.fields_changed[0]
    assert ch.key == "monthly_income"
    assert ch.from_status == FieldStatus.AMBIGUOUS
    assert ch.to_status == FieldStatus.SATISFIED
    assert ch.cause == "CLARIFICATION:INCOME_MISMATCH"

    # Verify audit events and clarification record in DB
    async with session_maker() as db:
        stmt = (
            select(AuditEventModel)
            .where(AuditEventModel.journey_id == UUID(journey_id))
            .order_by(AuditEventModel.created_at)
        )
        events = (await db.execute(stmt)).scalars().all()
        event_types = [e.event_type for e in events]
        assert AuditEventType.CLARIFICATION_ANSWERED.value in event_types

        clar_repo = ClarificationRepository(db)
        clar_records = await clar_repo.list_by_journey_id(UUID(journey_id))
        assert len(clar_records) == 1
        assert clar_records[0].ambiguity_id == "INCOME_MISMATCH"
        assert clar_records[0].field_key == "monthly_income"


@pytest.mark.asyncio
async def test_submit_clarification_multiple_ambiguities_chaining(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
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
    initial_snap_id = UUID(created_data["snapshot_id"])

    # 2. Setup snapshot with 2 ambiguous fields: monthly_income & employer_name
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        journey_repo = JourneyRepository(db)
        snap = await snap_repo.get_by_id(initial_snap_id)

        fields_copy = dict(snap.fields)
        fields_copy["employment_type"] = {
            "key": "employment_type",
            "label": "Employment Category",
            "status": "SATISFIED",
            "value": "SALARIED",
            "display_value": "Salaried",
            "explanation": "Verified",
            "resolve_action_id": "SUBMIT_EMPLOYMENT_INFO",
            "mandatory": True,
            "derived": False,
            "display": True,
        }
        fields_copy["monthly_income"] = {
            "key": "monthly_income",
            "label": "Monthly Income",
            "status": "AMBIGUOUS",
            "value": None,
            "display_value": None,
            "explanation": "Bank statement credit differs from salary slip",
            "resolve_action_id": "UPLOAD_INCOME_PROOF",
            "mandatory": True,
            "derived": False,
            "display": True,
            "ambiguity": {
                "ambiguity_id": "INCOME_MISMATCH",
                "field": "monthly_income",
                "reason": "Bank statement credit differs from salary slip",
                "question": "Which monthly income figure should be used for assessment?",
                "answer_type": "MONEY",
            },
        }
        fields_copy["employer_name"] = {
            "key": "employer_name",
            "label": "Employer Name",
            "status": "AMBIGUOUS",
            "value": None,
            "display_value": None,
            "explanation": "Employer organization name unverified",
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
            action_id="SETUP_TWO_AMBIGUITIES",
            previous_snapshot_id=initial_snap_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )
        amb_snap_1 = await snap_repo.create(
            token=token,
            readiness="NEEDS_REVIEW",
            fields=fields_copy,
            goal=snap.goal,
            pending_clarification={
                "ambiguity_id": "INCOME_MISMATCH",
                "field": "monthly_income",
                "reason": "Bank statement credit differs from salary slip",
                "question": "Which monthly income figure should be used for assessment?",
                "answer_type": "MONEY",
            },
        )
        await journey_repo.update_state(
            journey_id=UUID(journey_id),
            current_snapshot_id=amb_snap_1.id,
            readiness="NEEDS_REVIEW",
            status="IN_PROGRESS",
        )
        await db.commit()
        snap1_id = str(amb_snap_1.id)

    # 3. Resolve Ambiguity 1 (INCOME_MISMATCH)
    res1 = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 80000,
            "expected_snapshot_id": snap1_id,
        },
        headers=headers,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    resp1 = ActionResponse.model_validate(data1)

    # Readiness should still be NEEDS_REVIEW because employer_name is still AMBIGUOUS
    assert resp1.journey.readiness == Readiness.NEEDS_REVIEW
    assert resp1.journey.pending_clarification is not None
    assert resp1.journey.pending_clarification.ambiguity is not None
    assert resp1.journey.pending_clarification.ambiguity.ambiguity_id == "EMPLOYER_UNVERIFIED"
    assert resp1.journey.pending_clarification.key == "employer_name"

    snap2_id = str(resp1.journey.snapshot_id)

    # 4. Resolve Ambiguity 2 (EMPLOYER_UNVERIFIED)
    res2 = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "EMPLOYER_UNVERIFIED",
            "field": "employer_name",
            "answer": "Acme Corp India Private Limited",
            "expected_snapshot_id": snap2_id,
        },
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    resp2 = ActionResponse.model_validate(data2)

    # No more pending clarifications, readiness transitions out of NEEDS_REVIEW
    assert resp2.journey.readiness == Readiness.NOT_READY
    assert resp2.journey.pending_clarification is None
    emp_f = next(f for f in resp2.journey.fields if f.key == "employer_name")
    assert emp_f.status == FieldStatus.SATISFIED
    assert emp_f.value == "Acme Corp India Private Limited"


@pytest.mark.asyncio
async def test_submit_clarification_choice_validation_kyc(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # 1. Create KYC journey
    payload = {
        "journey_type": "KYC",
        "goal": {"kyc_purpose": "PERIODIC_UPDATE"},
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    journey_id = created_data["journey_id"]
    initial_snap_id = UUID(created_data["snapshot_id"])

    # 2. Setup AMB_EXPIRED_DOCUMENT ambiguity
    async with session_maker() as db:
        snap_repo = SnapshotRepository(db)
        journey_repo = JourneyRepository(db)
        snap = await snap_repo.get_by_id(initial_snap_id)

        fields_copy = dict(snap.fields)
        fields_copy["ovd_document_uploaded"] = {
            "key": "ovd_document_uploaded",
            "label": "Officially Valid Document (OVD)",
            "status": "AMBIGUOUS",
            "value": None,
            "display_value": None,
            "explanation": "OVD document issue date is more than 10 years old",
            "resolve_action_id": "upload_passport_ovd",
            "mandatory": True,
            "derived": False,
            "display": True,
            "ambiguity": {
                "ambiguity_id": "AMB_EXPIRED_DOCUMENT",
                "field": "ovd_document_uploaded",
                "reason": "OVD document issue date is more than 10 years old",
                "question": "Is your official document still active and valid?",
                "answer_type": "CHOICE",
                "choices": [
                    {"value": "VALID", "label": "Document is active and valid"},
                    {"value": "RENEWAL_PENDING", "label": "Renewal application pending"},
                ],
            },
        }
        token = CheckToken(
            token_id=uuid4(),
            journey_id=UUID(journey_id),
            journey_type="KYC",
            action_id="SETUP_KYC_AMBIGUITY",
            previous_snapshot_id=initial_snap_id,
            action_input={},
            new_values={},
            direct_fields=[],
            created_at=datetime.now(UTC),
        )
        amb_snap = await snap_repo.create(
            token=token,
            readiness="NEEDS_REVIEW",
            fields=fields_copy,
            goal=snap.goal,
            pending_clarification={
                "ambiguity_id": "AMB_EXPIRED_DOCUMENT",
                "field": "ovd_document_uploaded",
                "reason": "OVD document issue date is more than 10 years old",
                "question": "Is your official document still active and valid?",
                "answer_type": "CHOICE",
            },
        )
        await journey_repo.update_state(
            journey_id=UUID(journey_id),
            current_snapshot_id=amb_snap.id,
            readiness="NEEDS_REVIEW",
            status="IN_PROGRESS",
        )
        await db.commit()
        current_snap_id = str(amb_snap.id)

    # 3. Submit invalid choice -> 422
    bad_res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "AMB_EXPIRED_DOCUMENT",
            "field": "ovd_document_uploaded",
            "answer": "EXPIRED_AND_DISCARDED",
            "expected_snapshot_id": current_snap_id,
        },
        headers=headers,
    )
    assert bad_res.status_code == 422
    assert bad_res.json()["error"]["code"] == "ACTION_INVALID"

    # 4. Submit valid choice -> 200
    good_res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "AMB_EXPIRED_DOCUMENT",
            "field": "ovd_document_uploaded",
            "answer": "VALID",
            "expected_snapshot_id": current_snap_id,
        },
        headers=headers,
    )
    assert good_res.status_code == 200
    good_data = good_res.json()
    resp = ActionResponse.model_validate(good_data)
    ovd_f = next(f for f in resp.journey.fields if f.key == "ovd_document_uploaded")
    assert ovd_f.status == FieldStatus.SATISFIED
    assert ovd_f.value == "VALID"


@pytest.mark.asyncio
async def test_submit_clarification_stale_snapshot_409(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    # Create journey
    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    assert create_res.status_code == 201
    journey_id = create_res.json()["journey_id"]

    # Post with bogus snapshot ID
    res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 80000,
            "expected_snapshot_id": str(uuid4()),
        },
        headers=headers,
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ACTION_STALE"


@pytest.mark.asyncio
async def test_submit_clarification_invalid_ambiguity_or_field_422(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id = str(uuid4())
    headers = {"X-Session-Id": session_id}

    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_res = await client.post("/api/v1/journeys", json=payload, headers=headers)
    assert create_res.status_code == 201
    data = create_res.json()
    journey_id = data["journey_id"]
    snapshot_id = data["snapshot_id"]

    # Unknown ambiguity_id
    res1 = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "NON_EXISTENT_AMBIGUITY",
            "field": "monthly_income",
            "answer": 80000,
            "expected_snapshot_id": snapshot_id,
        },
        headers=headers,
    )
    assert res1.status_code == 422
    assert res1.json()["error"]["code"] == "ACTION_INVALID"

    # Mismatched field for INCOME_MISMATCH
    res2 = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "loan_amount",
            "answer": 80000,
            "expected_snapshot_id": snapshot_id,
        },
        headers=headers,
    )
    assert res2.status_code == 422
    assert res2.json()["error"]["code"] == "ACTION_INVALID"


@pytest.mark.asyncio
async def test_submit_clarification_cross_session_404(
    app_context: tuple[AsyncClient, async_sessionmaker],
):
    client, session_maker = app_context
    session_id_a = str(uuid4())
    session_id_b = str(uuid4())

    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_res = await client.post(
        "/api/v1/journeys", json=payload, headers={"X-Session-Id": session_id_a}
    )
    assert create_res.status_code == 201
    data = create_res.json()
    journey_id = data["journey_id"]
    snapshot_id = data["snapshot_id"]

    # Try submitting clarification from session_id_b -> 404
    res = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 80000,
            "expected_snapshot_id": snapshot_id,
        },
        headers={"X-Session-Id": session_id_b},
    )
    assert res.status_code == 404
