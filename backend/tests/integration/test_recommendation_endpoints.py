from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_recommendation_flow(client: AsyncClient, session_headers: dict[str, str]):
    # Create journey
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 300000,
            "loan_purpose": "EDUCATION",
            "tenure_months": 24,
        },
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    # Get recommendation
    rec_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=session_headers,
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["snapshot_id"] == snapshot_id
    assert rec_data["readiness"] == "NOT_READY"
    assert rec_data["recommendation"] is not None
    assert "action_id" in rec_data["recommendation"]
    assert "title" in rec_data["recommendation"]
    assert "why" in rec_data["recommendation"]
    assert "unlocks" in rec_data["recommendation"]
    assert isinstance(rec_data["alternatives"], list)
    assert rec_data["minimum_path_length"] >= 1


@pytest.mark.asyncio
async def test_get_recommendation_cross_session_404(
    client: AsyncClient,
    session_headers: dict[str, str],
    other_session_headers: dict[str, str],
):
    payload = {
        "journey_type": "INSURANCE",
        "goal": {
            "policy_type": "INDIVIDUAL",
            "sum_insured": 500000,
        },
    }
    resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert resp.status_code == 201
    journey_id = resp.json()["journey_id"]

    # Access from another session -> 404
    other_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation",
        headers=other_session_headers,
    )
    assert other_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_recommendation_nonexistent_404(
    client: AsyncClient, session_headers: dict[str, str]
):
    random_id = str(uuid4())
    resp = await client.get(
        f"/api/v1/journeys/{random_id}/recommendation",
        headers=session_headers,
    )
    assert resp.status_code == 404
