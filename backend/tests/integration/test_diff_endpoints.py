from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_diff_between_versions(client: AsyncClient, session_headers: dict[str, str]):
    # 1. Create journey (v1)
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

    # 2. Apply action (creates v2)
    action_payload = {
        "action_id": "SUBMIT_EMPLOYMENT_INFO",
        "expected_snapshot_id": snapshot_v1_id,
        "idempotency_key": str(uuid4()),
        "input": {
            "employment_type": "SALARIED",
            "employer_name": "Cognizant",
        },
    }
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json=action_payload,
        headers=session_headers,
    )
    assert act_resp.status_code == 200

    # 3. Query diff from=1 to=2
    diff_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/diff?from=1&to=2",
        headers=session_headers,
    )
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["from_version"] == 1
    assert diff_data["to_version"] == 2
    assert len(diff_data["fields_changed"]) >= 1
    assert any(fc["key"] == "employment_type" for fc in diff_data["fields_changed"])


@pytest.mark.asyncio
async def test_get_diff_missing_version_404(client: AsyncClient, session_headers: dict[str, str]):
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

    # Query diff for non-existent version 99
    diff_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/diff?from=1&to=99",
        headers=session_headers,
    )
    assert diff_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_diff_cross_session_404(
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

    # Cross session access -> 404
    diff_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/diff?from=1&to=1",
        headers=other_session_headers,
    )
    assert diff_resp.status_code == 404
