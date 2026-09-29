"""Regression tests: outside the test-fixture path, an EVIDENCE action must
reference real, server-verified evidence. Without the gate, a client could send
{"monthly_income": 999999} with no document and satisfy the income-proof field."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import settings


async def _create_lending(client: AsyncClient, headers: dict[str, str]) -> dict:
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 250000, "loan_purpose": "EDUCATION", "tenure_months": 36},
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_evidence_action_without_evidence_id_rejected_when_gate_closed(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE", False)
    journey = await _create_lending(client, session_headers)
    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": journey["snapshot_id"],
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 999999},
        },
        headers=session_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "ACTION_INVALID"

    state = await client.get(f"/api/v1/journeys/{journey['journey_id']}", headers=session_headers)
    assert state.json()["snapshot_id"] == journey["snapshot_id"]
    income = next(f for f in state.json()["fields"] if f["key"] == "monthly_income")
    assert income["status"] != "SATISFIED"


async def test_form_action_unaffected_when_gate_closed(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.packs.registry import pack_registry
    from app.schemas.enums import ActionKind

    monkeypatch.setattr(settings, "ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE", False)
    manifest = pack_registry.get_pack("LENDING")
    assert manifest is not None
    journey = await _create_lending(client, session_headers)
    form_ids = {a.action_id for a in manifest.actions if a.kind == ActionKind.FORM}
    rec = await client.get(
        f"/api/v1/journeys/{journey['journey_id']}/recommendation", headers=session_headers
    )
    options = [rec.json().get("recommendation")] + rec.json().get("alternatives", [])
    form = next((o for o in options if o and o["action_id"] in form_ids), None)
    if form is None:
        pytest.skip("No FORM action executable at LENDING v1")
    values = {f["key"]: "Example" for f in (form.get("input_schema") or [])}
    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": form["action_id"],
            "expected_snapshot_id": journey["snapshot_id"],
            "idempotency_key": str(uuid4()),
            "input": values,
        },
        headers=session_headers,
    )
    assert (
        resp.status_code != 422 or resp.json()["error"]["details"].get("missing") != "evidence_id"
    )


def test_gate_defaults_closed_outside_local_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.journey_service import _evidence_less_actions_allowed

    monkeypatch.setattr(settings, "ALLOW_EVIDENCE_ACTIONS_WITHOUT_EVIDENCE", None)
    monkeypatch.setattr(settings, "APP_ENV", "production")
    assert _evidence_less_actions_allowed() is False
    monkeypatch.setattr(settings, "APP_ENV", "ci")
    assert _evidence_less_actions_allowed() is True


async def test_clarification_rejected_when_no_ambiguity_is_open(
    client: AsyncClient, session_headers: dict
) -> None:
    journey = await _create_lending(client, session_headers)
    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/clarifications",
        json={
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "monthly_income",
            "answer": 999999999,
            "expected_snapshot_id": journey["snapshot_id"],
        },
        headers=session_headers,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "ACTION_INVALID"

    state = await client.get(f"/api/v1/journeys/{journey['journey_id']}", headers=session_headers)
    assert state.json()["snapshot_id"] == journey["snapshot_id"]
    income = next(f for f in state.json()["fields"] if f["key"] == "monthly_income")
    assert income["value"] != 999999999
    assert income["status"] != "SATISFIED"


async def test_clarification_for_a_different_open_ambiguity_rejected(
    client: AsyncClient, session_headers: dict
) -> None:
    journey = await _create_lending(client, session_headers)
    opened = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": journey["snapshot_id"],
            "idempotency_key": str(uuid4()),
            "input": {"monthly_income": 60000, "ambiguity_id": "INCOME_MISMATCH"},
        },
        headers=session_headers,
    )
    assert opened.status_code == 200, opened.text
    snap = opened.json()["journey"]["snapshot_id"]
    resp = await client.post(
        f"/api/v1/journeys/{journey['journey_id']}/clarifications",
        json={
            "ambiguity_id": "EMPLOYER_UNVERIFIED",
            "field": "employer_name",
            "answer": "Anything Pvt Ltd",
            "expected_snapshot_id": snap,
        },
        headers=session_headers,
    )
    assert resp.status_code == 422, resp.text
