from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_journey_lifecycle(
    client: AsyncClient, session_headers: dict[str, str]
):
    # 1. Create a Lending journey
    payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 250000,
            "loan_purpose": "DEBT_CONSOLIDATION",
            "tenure_months": 36,
        },
    }
    resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert resp.status_code == 201
    data = resp.json()
    journey_id = data["journey_id"]
    snapshot_id = data["snapshot_id"]
    assert data["journey_type"] == "LENDING"
    assert data["version_number"] == 1
    assert data["readiness"] == "NOT_READY"
    assert data["status"] == "IN_PROGRESS"
    assert len(data["fields"]) > 0
    assert data["display"]["title"] == "Personal Loan"

    # 2. Get the created journey by ID
    get_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["journey_id"] == journey_id
    assert get_data["snapshot_id"] == snapshot_id
    assert get_data["version_number"] == 1


@pytest.mark.asyncio
async def test_list_journeys_scoped_and_filtered(
    client: AsyncClient, session_headers: dict[str, str]
):
    # Create two journeys for session A
    lending_payload = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 100000,
            "loan_purpose": "MEDICAL_EXPENSES",
            "tenure_months": 12,
        },
    }
    await client.post("/api/v1/journeys", json=lending_payload, headers=session_headers)

    card_payload = {
        "journey_type": "CREDIT_CARD",
        "goal": {
            "card_variant": "CASHBACK",
            "credit_limit_preference": 50000,
        },
    }
    await client.post("/api/v1/journeys", json=card_payload, headers=session_headers)

    # List all for session A
    list_resp = await client.get("/api/v1/journeys", headers=session_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert len(list_data["journeys"]) >= 2

    # Filter by journey_type
    lending_resp = await client.get(
        "/api/v1/journeys?journey_type=LENDING",
        headers=session_headers,
    )
    assert lending_resp.status_code == 200
    lending_data = lending_resp.json()
    assert all(j["journey_type"] == "LENDING" for j in lending_data["journeys"])

    # Filter by status
    status_resp = await client.get(
        "/api/v1/journeys?status=IN_PROGRESS",
        headers=session_headers,
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert all(j["status"] == "IN_PROGRESS" for j in status_data["journeys"])


@pytest.mark.asyncio
async def test_journey_cross_session_isolation(
    client: AsyncClient,
    session_headers: dict[str, str],
    other_session_headers: dict[str, str],
):
    # Create journey in Session A
    payload = {
        "journey_type": "KYC",
        "goal": {
            "kyc_purpose": "PERIODIC_UPDATE",
        },
    }
    resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert resp.status_code == 201
    journey_id = resp.json()["journey_id"]

    # Session B tries to access Session A's journey -> 404 (indistinguishable from not found)
    other_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=other_session_headers)
    assert other_resp.status_code == 404

    # Session B listing does not include Session A's journey
    other_list = await client.get("/api/v1/journeys", headers=other_session_headers)
    assert other_list.status_code == 200
    other_journey_ids = [j["journey_id"] for j in other_list.json()["journeys"]]
    assert journey_id not in other_journey_ids


@pytest.mark.asyncio
async def test_create_journey_validation_errors(
    client: AsyncClient, session_headers: dict[str, str]
):
    # Missing required goal field
    invalid_goal = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            # missing loan_purpose and tenure_months
        },
    }
    resp = await client.post("/api/v1/journeys", json=invalid_goal, headers=session_headers)
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"

    # Unknown goal field
    unknown_field_goal = {
        "journey_type": "LENDING",
        "goal": {
            "loan_amount": 200000,
            "loan_purpose": "EDUCATION",
            "tenure_months": 24,
            "hacker_field": "injected",
        },
    }
    resp2 = await client.post("/api/v1/journeys", json=unknown_field_goal, headers=session_headers)
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_nonexistent_journey_returns_404(
    client: AsyncClient, session_headers: dict[str, str]
):
    random_id = str(uuid4())
    resp = await client.get(f"/api/v1/journeys/{random_id}", headers=session_headers)
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
