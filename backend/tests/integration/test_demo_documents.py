"""Proves the two committed judge-facing SYNTHETIC DEMO DOCUMENTS
(frontend/public/demo-documents/) are not a fake shortcut: they are
submitted through the REAL POST /journeys/{id}/evidence HTTP endpoint,
with AI_PROVIDER=local_ml (the real OCR + classifier + extractor
pipeline, not MockAI), and must genuinely classify and extract correctly
- exactly as any real judge's upload would.

The final test walks the ENTIRE flagship LENDING journey to READY using
ONLY these two documents plus the two plain FORM actions that don't
require any document (employment_type, accept_terms) - proving a judge
really can complete the real journey without a real financial document.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import settings
from app.docai.classifier import get_classifier

DEMO_DOCS_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "demo-documents"

pytestmark = [
    pytest.mark.skipif(
        get_classifier("LENDING") is None, reason="No trained LENDING classifier present."
    ),
    pytest.mark.asyncio,
]


def _read_demo_doc(name: str) -> bytes:
    path = DEMO_DOCS_DIR / name
    assert path.exists(), f"Demo document missing: {path}"
    return path.read_bytes()


async def _create_lending_journey(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=headers)
    assert create_resp.status_code == 201
    body = create_resp.json()
    return body["journey_id"], body["snapshot_id"]


async def test_demo_salary_slip_is_genuinely_classified_and_extracted(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")
    journey_id, snapshot_id = await _create_lending_journey(client, session_headers)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snapshot_id},
        files={
            "file": (
                "sample-salary-slip.pdf",
                _read_demo_doc("sample-salary-slip.pdf"),
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["interpretation"]["verified"] is True
    detected = {d["key"]: d["display_value"] for d in body["interpretation"]["detected"]}
    assert detected.get("monthly_income") == "₹85,000"


async def test_demo_offer_letter_is_genuinely_classified_and_extracted(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")
    journey_id, snapshot_id = await _create_lending_journey(client, session_headers)

    # employer_name is only unblocked after employment_type is declared
    # (dependencies: employment_type -> employer_name), so the FORM step
    # runs first, exactly like a real journey.
    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "SALARIED"},
        },
        headers=session_headers,
    )
    assert act_resp.status_code == 200
    snapshot_id = act_resp.json()["journey"]["snapshot_id"]

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "OFFER_LETTER", "expected_snapshot_id": snapshot_id},
        files={
            "file": (
                "sample-offer-letter.pdf",
                _read_demo_doc("sample-offer-letter.pdf"),
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["interpretation"]["verified"] is True
    detected = {d["key"]: d["display_value"] for d in body["interpretation"]["detected"]}
    assert detected.get("employer_name") == "Acme Technologies India Pvt Ltd"


async def test_judge_can_complete_the_real_lending_journey_using_only_demo_documents(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """End-to-end proof: a judge with no real financial documents can
    still drive the flagship LENDING journey all the way to READY using
    only the two committed synthetic demo documents plus the two
    document-free FORM actions - no shortcut, no fake result."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")
    journey_id, snapshot_id = await _create_lending_journey(client, session_headers)

    # 1. Income proof via the demo salary slip (EVIDENCE).
    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snapshot_id},
        files={
            "file": (
                "sample-salary-slip.pdf",
                _read_demo_doc("sample-salary-slip.pdf"),
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    evidence_id_income = ev_resp.json()["evidence_id"]

    act1_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id_income},
        },
        headers=session_headers,
    )
    assert act1_resp.status_code == 200
    snapshot_id = act1_resp.json()["journey"]["snapshot_id"]

    # 2. Employment type (FORM, no document needed).
    act2_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "SUBMIT_EMPLOYMENT_INFO",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"employment_type": "SALARIED"},
        },
        headers=session_headers,
    )
    assert act2_resp.status_code == 200
    snapshot_id = act2_resp.json()["journey"]["snapshot_id"]

    # 3. Employer verification via the demo offer letter (EVIDENCE).
    ev_resp2 = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "OFFER_LETTER", "expected_snapshot_id": snapshot_id},
        files={
            "file": (
                "sample-offer-letter.pdf",
                _read_demo_doc("sample-offer-letter.pdf"),
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert ev_resp2.status_code == 200
    evidence_id_employer = ev_resp2.json()["evidence_id"]

    act3_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_WORK_ID",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id_employer},
        },
        headers=session_headers,
    )
    assert act3_resp.status_code == 200
    snapshot_id = act3_resp.json()["journey"]["snapshot_id"]

    # 4. Accept loan terms (FORM, no document needed) -> READY.
    act4_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "ACCEPT_LOAN_TERMS",
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": {"accept_terms": True},
        },
        headers=session_headers,
    )
    assert act4_resp.status_code == 200
    assert act4_resp.json()["journey"]["readiness"] == "READY"
