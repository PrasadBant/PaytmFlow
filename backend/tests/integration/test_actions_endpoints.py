from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_apply_action_success_and_idempotency_replay(
    client: AsyncClient,
    session_headers: dict[str, str],
):
    # 1. Create journey
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_v1_id = create_resp.json()["snapshot_id"]

    # 2. Apply action: SUBMIT_EMPLOYMENT_INFO
    idempotency_key = str(uuid4())
    action_payload = {
        "action_id": "SUBMIT_EMPLOYMENT_INFO",
        "expected_snapshot_id": snapshot_v1_id,
        "idempotency_key": idempotency_key,
        "input": {
            "employment_type": "SALARIED",
            "employer_name": "Infosys Ltd",
        },
    }
    resp1 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=session_headers,
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["journey"]["version_number"] == 2
    snapshot_v2_id = data1["journey"]["snapshot_id"]
    assert snapshot_v2_id != snapshot_v1_id
    assert "diff" in data1
    assert data1["diff"]["from_version"] == 1
    assert data1["diff"]["to_version"] == 2
    assert "next_recommendation" in data1

    # 3. Replay EXACT same request with same idempotency_key -> returns identical body
    resp2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=session_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2 == data1
    assert data2["journey"]["snapshot_id"] == snapshot_v2_id

    # Verify state in DB remains at version 2 (no version 3 created)
    get_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["version_number"] == 2


@pytest.mark.asyncio
async def test_apply_action_stale_snapshot_409(
    client: AsyncClient, session_headers: dict[str, str]
):
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]

    stale_snapshot_id = str(uuid4())
    action_payload = {
        "action_id": "SUBMIT_EMPLOYMENT_INFO",
        "expected_snapshot_id": stale_snapshot_id,
        "idempotency_key": str(uuid4()),
        "input": {
            "employment_type": "SALARIED",
            "employer_name": "TCS",
        },
    }
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=session_headers,
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["error"]["code"] == "ACTION_STALE"


@pytest.mark.asyncio
async def test_apply_action_invalid_preconditions_422(
    client: AsyncClient, session_headers: dict[str, str]
):
    # Try to execute ACCEPT_OFFER directly at v1 without income/offer (preconditions not satisfied)
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    action_payload = {
        "action_id": "ACCEPT_OFFER",
        "expected_snapshot_id": snapshot_id,
        "idempotency_key": str(uuid4()),
        "input": {"offer_accepted": True},
    }
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=session_headers,
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "ACTION_INVALID"


@pytest.mark.asyncio
async def test_apply_action_cross_session_404(
    client: AsyncClient,
    session_headers: dict[str, str],
    other_session_headers: dict[str, str],
):
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "HOME_RENOVATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    action_payload = {
        "action_id": "SUBMIT_EMPLOYMENT_INFO",
        "expected_snapshot_id": snapshot_id,
        "idempotency_key": str(uuid4()),
        "input": {
            "employment_type": "SALARIED",
            "employer_name": "Wipro",
        },
    }
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=other_session_headers,
    )
    assert resp.status_code == 404
