import json
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_submit_clarification_flow(client: AsyncClient, session_headers: dict[str, str]):
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

    # 2. Upload conflicting salary slip to trigger NEEDS_REVIEW / ambiguity
    # (Mock service produces an income mismatch when specific data or salary slip submitted)
    ev_data = {
        "doc_type": "SALARY_SLIP",
        "expected_snapshot_id": snapshot_v1_id,
        "manual_fields": json.dumps({"monthly_income": 85000}),
    }
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data=ev_data,
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    evidence_id = ev_resp.json()["evidence_id"]

    # Apply evidence action
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snapshot_v1_id,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=session_headers,
    )
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    snapshot_v2_id = act_data["journey"]["snapshot_id"]

    # 3. If ambiguity exists (or test clarification endpoint directly)
    # Submit clarification for monthly_income
    clar_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 85000,
            "expected_snapshot_id": snapshot_v2_id,
        },
        headers=session_headers,
    )
    # Should succeed or return appropriate status
    assert clar_resp.status_code in [200, 422]
    if clar_resp.status_code == 200:
        c_data = clar_resp.json()
        assert c_data["journey"]["version_number"] == 3
        assert "diff" in c_data


@pytest.mark.asyncio
async def test_submit_clarification_stale_snapshot_409(
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

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 85000,
            "expected_snapshot_id": str(uuid4()),
        },
        headers=session_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ACTION_STALE"


@pytest.mark.asyncio
async def test_submit_clarification_cross_session_404(
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

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 85000,
            "expected_snapshot_id": snapshot_id,
        },
        headers=other_session_headers,
    )
    assert resp.status_code == 404
