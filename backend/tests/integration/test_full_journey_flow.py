import json
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_lending_golden_path_end_to_end_integration(client: AsyncClient):
    # 1. Health & Session boot
    health_resp = await client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["packs_loaded"] == 6

    session_resp = await client.get("/api/v1/session")
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]
    headers = {"X-Session-Id": session_id}

    # 2. Get Pack detail
    pack_resp = await client.get("/api/v1/journey-packs/LENDING")
    assert pack_resp.status_code == 200

    # 3. Create Journey
    create_payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=create_payload, headers=headers)
    assert create_resp.status_code == 201
    journey_data = create_resp.json()
    journey_id = journey_data["journey_id"]
    curr_snap_id = journey_data["snapshot_id"]
    assert journey_data["version_number"] == 1
    assert journey_data["readiness"] == "NOT_READY"

    # 4. Check recommendation
    rec_resp = await client.get(f"/api/v1/journeys/{journey_id}/recommendation", headers=headers)
    assert rec_resp.status_code == 200
    assert rec_resp.json()["recommendation"] is not None

    # 5. Submit Evidence (Salary Slip)
    ev_data = {
        "doc_type": "SALARY_SLIP",
        "expected_snapshot_id": curr_snap_id,
        "manual_fields": json.dumps({"monthly_income": 85000}),
    }
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data=ev_data,
        headers=headers,
    )
    assert ev_resp.status_code == 200
    evidence_id = ev_resp.json()["evidence_id"]

    # 6. Action 1: UPLOAD_INCOME_PROOF
    act1_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": curr_snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=headers,
    )
    assert act1_resp.status_code == 200
    curr_snap_id = act1_resp.json()["journey"]["snapshot_id"]
    assert act1_resp.json()["journey"]["version_number"] == 2

    # 7. Action 2: SUBMIT_EMPLOYMENT_INFO
    act2_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": curr_snap_id,
            "idempotency_key": str(uuid4()),
            "input": {
                "employment_type": "SALARIED",
            },
        },
        headers=headers,
    )
    assert act2_resp.status_code == 200
    curr_snap_id = act2_resp.json()["journey"]["snapshot_id"]
    assert act2_resp.json()["journey"]["version_number"] == 3

    # 8. Action 3: VERIFY_EMPLOYER_RECORD
    act3_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "VERIFY_EMPLOYER_RECORD",
            "expected_snapshot_id": curr_snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"employer_name": "Infosys Ltd"},
        },
        headers=headers,
    )
    assert act3_resp.status_code == 200
    curr_snap_id = act3_resp.json()["journey"]["snapshot_id"]
    assert act3_resp.json()["journey"]["version_number"] == 4

    # 9. Action 4: ACCEPT_LOAN_TERMS
    act4_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": curr_snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=headers,
    )
    assert act4_resp.status_code == 200
    final_journey = act4_resp.json()["journey"]
    assert final_journey["version_number"] == 5
    assert final_journey["readiness"] == "READY"
    assert final_journey["status"] == "COMPLETED"

    # 10. Query diff from=1 to=5
    diff_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/diff?from=1&to=5",
        headers=headers,
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["from_version"] == 1
    assert diff_data["to_version"] == 5
    assert diff_data["readiness"]["to"] == "READY"
    assert diff_data["progress"]["to"]["completed"] == 7
    assert diff_data["progress"]["to"]["pending"] == 0

    # 11. Final recommendation check on completed journey -> recommendation is None
    final_rec_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=headers,
    )
    assert final_rec_resp.status_code == 200
    assert final_rec_resp.json()["readiness"] == "READY"
    assert final_rec_resp.json()["recommendation"] is None
