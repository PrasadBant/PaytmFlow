import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_db
from app.main import app


@pytest.mark.asyncio
async def test_progress_persistence_and_session_isolation(db_engine):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    try:
        transport = ASGITransport(app=app)

        # User 1 session
        async with AsyncClient(transport=transport, base_url="http://test") as client1:
            # Step 1: Initialize session
            sess_resp = await client1.get("/api/v1/session")
            assert sess_resp.status_code == 200

            # Step 2: Create one journey
            create_resp = await client1.post(
                "/api/v1/journeys",
                json={
                    "journey_type": "LENDING",
                    "goal": {
                        "loan_amount": 500000,
                        "loan_purpose": "HOME_RENOVATION",
                        "tenure_months": 36,
                    },
                },
            )
            assert create_resp.status_code == 201
            data = create_resp.json()
            journey_id = data["journey_id"]
            snap_v1 = data["snapshot_id"]
            init_completed = data["progress"]["completed"]
            init_total = data["progress"]["total"]
            # 3 initial satisfied fields out of 7 total fields
            assert init_completed == 3
            assert init_total == 7

            # Step 3: GET /journeys (verify read-only, same journey)
            list_resp = await client1.get("/api/v1/journeys")
            assert list_resp.status_code == 200
            journeys = list_resp.json()["journeys"]
            assert len([j for j in journeys if j["journey_id"] == journey_id]) == 1
            item = next(j for j in journeys if j["journey_id"] == journey_id)
            assert item["progress"]["completed"] == 3

            # Repeated GET /journeys does not create another journey
            list_resp2 = await client1.get("/api/v1/journeys")
            assert len(list_resp2.json()["journeys"]) == len(journeys)

            # Step 4: Complete one action (SUBMIT_EMPLOYMENT_INFO)
            act1_resp = await client1.post(
                f"/api/v1/journeys/{journey_id}/actions",
                json={
                    "action_id": "SUBMIT_EMPLOYMENT_INFO",
                    "expected_snapshot_id": snap_v1,
                    "idempotency_key": "11111111-1111-4111-8111-111111111111",
                    "input": {"employment_type": "SALARIED"},
                },
            )
            assert act1_resp.status_code == 200
            act1_data = act1_resp.json()
            snap_v2 = act1_data["journey"]["snapshot_id"]
            assert act1_data["journey"]["progress"]["completed"] == 4

            # Step 5: Reload / GET /journeys (progress remains 4/7)
            list_resp3 = await client1.get("/api/v1/journeys")
            item = next(j for j in list_resp3.json()["journeys"] if j["journey_id"] == journey_id)
            assert item["progress"]["completed"] == 4
            assert item["snapshot_id"] if "snapshot_id" in item else True

            # Step 6: Complete another action (VERIFY_EMPLOYER_RECORD)
            act2_resp = await client1.post(
                f"/api/v1/journeys/{journey_id}/actions",
                json={
                    "action_id": "VERIFY_EMPLOYER_RECORD",
                    "expected_snapshot_id": snap_v2,
                    "idempotency_key": "22222222-2222-4222-8222-222222222222",
                    "input": {"employer_name": "One97 Communications"},
                },
            )
            assert act2_resp.status_code == 200
            act2_data = act2_resp.json()
            snap_v3 = act2_data["journey"]["snapshot_id"]
            assert act2_data["journey"]["progress"]["completed"] == 5

            # Step 7: Reload / GET /journeys (progress remains 5/7)
            list_resp4 = await client1.get("/api/v1/journeys")
            item = next(j for j in list_resp4.json()["journeys"] if j["journey_id"] == journey_id)
            assert item["progress"]["completed"] == 5

            # Step 8: Complete remaining actions to 7/7
            act3_resp = await client1.post(
                f"/api/v1/journeys/{journey_id}/actions",
                json={
                    "action_id": "LINK_AA_ACCOUNT",
                    "expected_snapshot_id": snap_v3,
                    "idempotency_key": "33333333-3333-4333-8333-333333333333",
                    "input": {"consent_handle": "CONSENT_AA_9988"},
                },
            )
            assert act3_resp.status_code == 200
            act3_data = act3_resp.json()
            snap_v4 = act3_data["journey"]["snapshot_id"]
            assert act3_data["journey"]["progress"]["completed"] == 6

            act4_resp = await client1.post(
                f"/api/v1/journeys/{journey_id}/actions",
                json={
                    "action_id": "ACCEPT_LOAN_TERMS",
                    "expected_snapshot_id": snap_v4,
                    "idempotency_key": "44444444-4444-4444-8444-444444444444",
                    "input": {"accept_terms": True},
                },
            )
            assert act4_resp.status_code == 200
            act4_data = act4_resp.json()
            assert act4_data["journey"]["progress"]["completed"] == 7
            assert act4_data["journey"]["readiness"] == "READY"
            assert act4_data["journey"]["status"] == "COMPLETED"

            # Step 9: Reload / GET /journeys (persists as completed 7/7)
            list_resp5 = await client1.get("/api/v1/journeys")
            item = next(j for j in list_resp5.json()["journeys"] if j["journey_id"] == journey_id)
            assert item["progress"]["completed"] == 7
            assert item["status"] == "COMPLETED"

        # Step 10: Cross-session isolation
        async with AsyncClient(transport=transport, base_url="http://test") as client2:
            sess_resp2 = await client2.get("/api/v1/session")
            assert sess_resp2.status_code == 200
            # Client 2 must NOT see Client 1's journey
            list_resp_c2 = await client2.get("/api/v1/journeys")
            assert list_resp_c2.status_code == 200
            c2_journeys = list_resp_c2.json()["journeys"]
            assert not any(j["journey_id"] == journey_id for j in c2_journeys)
    finally:
        app.dependency_overrides.clear()
