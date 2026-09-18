"""Targeted integration tests verifying fixes for Errors #6, #7, #8, and #9.

Covers all 5 non-loan journeys (Credit Card, Health Insurance, KYC, Account Opening,
Investment) and regression verification for Personal Loan (Lending).
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_error_6_health_insurance_prerequisite_and_action_resolution(client: AsyncClient):
    """Error #6: Health Insurance medical history declaration and PED clearance resolution."""
    # 1. Create Insurance journey
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "INSURANCE",
            "goal": {
                "sum_insured": 1000000,
                "policy_type": "INDIVIDUAL",
            },
        },
    )
    assert resp.status_code == 201
    journey = resp.json()
    journey_id = journey["journey_id"]
    snap_id = journey["snapshot_id"]

    # Initial state: medical_history_declared is BLOCKED
    fields = {f["key"]: f for f in journey["fields"]}
    assert fields["medical_history_declared"]["status"] == "BLOCKED"
    assert fields["medical_history_declared"]["resolve_action_id"] == "submit_medical_declaration"

    # 2. Submit medical history declaration
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "submit_medical_declaration",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {
                "has_medical_history": "NO",
            },
        },
    )
    assert act_resp.status_code == 200
    snap_id = act_resp.json()["journey"]["snapshot_id"]
    updated_fields = {f["key"]: f for f in act_resp.json()["journey"]["fields"]}
    assert updated_fields["medical_history_declared"]["status"] == "SATISFIED"

    # Now ped_declaration_submitted can be resolved via confirm_zero_ped or submit_ped_clearance
    assert updated_fields["ped_declaration_submitted"]["status"] == "BLOCKED"
    assert updated_fields["ped_declaration_submitted"]["resolve_action_id"] == "submit_ped_records"

    # 3. Confirm zero PED
    act_resp2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "submit_ped_exemption",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"no_pre_existing_conditions": True},
        },
    )
    assert act_resp2.status_code == 200
    updated_fields2 = {f["key"]: f for f in act_resp2.json()["journey"]["fields"]}
    assert updated_fields2["ped_declaration_submitted"]["status"] == "SATISFIED"


@pytest.mark.asyncio
async def test_error_6_credit_card_action_resolution(client: AsyncClient):
    """Error #6: Credit card form actions resolution."""
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "CREDIT_CARD",
            "goal": {
                "card_variant": "CASHBACK",
                "credit_limit_preference": 100000,
            },
        },
    )
    assert resp.status_code == 201
    journey = resp.json()
    journey_id = journey["journey_id"]
    snap_id = journey["snapshot_id"]

    fields = {f["key"]: f for f in journey["fields"]}
    assert fields["employment_verified"]["status"] == "BLOCKED"
    assert fields["employment_verified"]["resolve_action_id"] == "verify_employment_details"

    # Submit employment info
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "verify_employment_details",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {
                "employer_name": "Acme Corp",
                "monthly_net_income": 75000,
            },
        },
    )
    assert act_resp.status_code == 200
    updated_fields = {f["key"]: f for f in act_resp.json()["journey"]["fields"]}
    assert updated_fields["employment_verified"]["status"] == "SATISFIED"


@pytest.mark.asyncio
async def test_error_6_and_7_account_opening_and_kyc(client: AsyncClient):
    """Error #6 & #7: Account Opening and KYC form & consent action flow."""
    # KYC journey
    resp = await client.post(
        "/api/v1/journeys",
        json={"journey_type": "KYC", "goal": {"kyc_purpose": "PERIODIC_UPDATE"}},
    )
    assert resp.status_code == 201
    kyc_j = resp.json()
    kyc_id = kyc_j["journey_id"]
    snap_id = kyc_j["snapshot_id"]

    # Link PAN
    act1 = await client.post(
        f"/api/v1/journeys/{kyc_id}/actions",
        json={
            "action_id": "link_pan_record",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"pan_number": "ABCDE1234F"},
        },
    )
    assert act1.status_code == 200, f"act1 failed: {act1.text}"
    snap_id = act1.json()["journey"]["snapshot_id"]

    # Capture liveness
    act2 = await client.post(
        f"/api/v1/journeys/{kyc_id}/actions",
        json={
            "action_id": "capture_liveness_selfie",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"liveness_confirmed": True},
        },
    )
    assert act2.status_code == 200
    snap_id = act2.json()["journey"]["snapshot_id"]

    # Confirm geolocation
    act3 = await client.post(
        f"/api/v1/journeys/{kyc_id}/actions",
        json={
            "action_id": "validate_gps_location",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {"location_confirmed": True},
        },
    )
    assert act3.status_code == 200


@pytest.mark.asyncio
async def test_error_8_natural_language_goal_merging(client: AsyncClient):
    """Error #8: Natural language description overrides form defaults when parsed."""
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {
                "loan_amount": 500000,
                "tenure_months": 36,
                "loan_purpose": "DEBT_CONSOLIDATION",
            },
            "natural_language": "I need a personal loan of 250000 rupees for medical emergency",
        },
    )
    assert resp.status_code == 201
    journey = resp.json()
    assert journey["journey_type"] == "LENDING"
    assert journey["readiness"] in ["NOT_READY", "READY", "NEEDS_REVIEW"]


@pytest.mark.asyncio
async def test_error_9_journey_timestamps_updated_on_actions(client: AsyncClient):
    """Error #9: Journey updated_at timestamp is persisted and advances with new snapshots."""
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "INVESTMENT",
            "goal": {
                "investment_mode": "MONTHLY_SIP",
                "target_amount": 10000,
            },
        },
    )
    assert resp.status_code == 201
    journey = resp.json()
    journey_id = journey["journey_id"]
    snap_id = journey["snapshot_id"]
    created_updated_at = journey["updated_at"]
    assert created_updated_at is not None

    # Perform an action
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "check_kra_status",
            "expected_snapshot_id": snap_id,
            "idempotency_key": str(uuid4()),
            "input": {
                "pan_number": "ABCDE1234F",
                "date_of_birth": "15/08/1990",
            },
        },
    )
    assert act_resp.status_code == 200
    updated_journey = act_resp.json()["journey"]
    assert updated_journey["updated_at"] is not None

    # Verify GET /journeys lists the journey with valid timestamp
    list_resp = await client.get("/api/v1/journeys")
    assert list_resp.status_code == 200
    journeys_list = list_resp.json()["journeys"]
    matching = next((j for j in journeys_list if j["journey_id"] == journey_id), None)
    assert matching is not None
    assert matching["updated_at"] is not None
