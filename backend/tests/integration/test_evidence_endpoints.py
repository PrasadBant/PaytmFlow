import json
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_evidence_manual_fields_preview(
    client: AsyncClient, session_headers: dict[str, str]
):
    # Create journey
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
    snapshot_id = create_resp.json()["snapshot_id"]

    # Submit evidence via manual_fields
    manual_fields = json.dumps({"monthly_income": 75000, "employer_name": "Tech Corp"})
    data = {
        "doc_type": "SALARY_SLIP",
        "expected_snapshot_id": snapshot_id,
        "manual_fields": manual_fields,
    }
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data=data,
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert "evidence_id" in ev_data
    assert "interpretation" in ev_data
    assert "detected" in ev_data["interpretation"]
    assert "consequence_preview" in ev_data

    # Verify no snapshot was created by evidence upload
    get_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["snapshot_id"] == snapshot_id
    assert get_resp.json()["version_number"] == 1


@pytest.mark.asyncio
async def test_upload_evidence_stale_snapshot_409(
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
    data = {
        "doc_type": "SALARY_SLIP",
        "expected_snapshot_id": stale_snapshot_id,
        "manual_fields": json.dumps({"monthly_income": 50000}),
    }
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data=data,
        headers=session_headers,
    )
    assert ev_resp.status_code == 409
    assert ev_resp.json()["error"]["code"] == "ACTION_STALE"


@pytest.mark.asyncio
async def test_upload_evidence_cross_session_404(
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

    data = {
        "doc_type": "SALARY_SLIP",
        "expected_snapshot_id": snapshot_id,
        "manual_fields": json.dumps({"monthly_income": 50000}),
    }
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data=data,
        headers=other_session_headers,
    )
    assert ev_resp.status_code == 404
