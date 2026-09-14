"""Final unseen-document evaluation (Phase 13, docs/docai_final_unseen_error_analysis.md
Part 4): pushes GENUINELY held-out `unseen_template` images - never seen during
classifier training, never used in any prior E2E/integrity test - through the
REAL production HTTP path (evidence endpoint -> OCR -> classifier -> extraction
-> normalization -> validation -> persisted evidence -> action endpoint ->
deterministic engine), to confirm the P1 Document AI integration fix
(docs/docai_e2e_integration_fix_report.md) holds for documents the model has
never encountered in any form, not just freshly-rendered variants of known
templates (as test_docai_e2e_journeys.py and test_evidence_action_integrity.py
already exercise).

Uses Lending's on-disk `data/docai/lending/unseen_template/` images directly -
no synthetic generation, no cherry-picking beyond selecting one genuinely
correct case and one genuinely wrong-document case from the existing labels.
"""

from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import settings
from app.docai.classifier import get_classifier
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier."),
    pytest.mark.asyncio,
]

LENDING_UNSEEN = (
    Path(__file__).resolve().parents[2] / "data" / "docai" / "lending" / "unseen_template"
)

# Genuinely held-out sample: never used in training/val/test, never rendered
# freshly for any other test in this repository.
CORRECT_SALARY_SLIP = "SALARY_SLIP_salary_takehome_0049.jpg"
CORRECT_SALARY_SLIP_INCOME = 77000  # ground truth, from unseen_template/labels.jsonl

# Genuinely wrong document for an income-proof action: a real OFFICE_ID_CARD,
# also from the held-out unseen_template split.
WRONG_DOC_FOR_INCOME = "OFFICE_ID_CARD_id_qr_unseen_0153.jpg"


async def _create_lending_journey(client: AsyncClient, headers: dict):
    resp = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()["journey_id"], resp.json()["snapshot_id"]


async def test_unseen_correct_document_advances_state_with_real_extracted_value(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """A genuinely unseen-template SALARY_SLIP (never used in training) must
    still classify correctly, extract the real income, and drive the
    deterministic engine to the actual extracted value - not a fabricated one."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    image_bytes = (LENDING_UNSEEN / CORRECT_SALARY_SLIP).read_bytes()

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={"file": (CORRECT_SALARY_SLIP, image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200, ev_resp.text
    evidence_id = ev_resp.json()["evidence_id"]

    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=session_headers,
    )
    assert act_resp.status_code == 200, act_resp.text
    income_field = next(
        f for f in act_resp.json()["journey"]["fields"] if f["key"] == "monthly_income"
    )
    assert income_field["value"] == CORRECT_SALARY_SLIP_INCOME
    assert income_field["value"] != 85000  # not the manifest's simulation default


async def test_unseen_wrong_document_never_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """A genuinely unseen-template WRONG document (a real OFFICE_ID_CARD)
    submitted for an income-proof action must never advance journey state,
    never receive a simulation default, and never fabricate monthly_income."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    image_bytes = (LENDING_UNSEEN / WRONG_DOC_FOR_INCOME).read_bytes()

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "OFFICE_ID_CARD", "expected_snapshot_id": snap},
        files={"file": (WRONG_DOC_FOR_INCOME, image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200, ev_resp.text
    evidence_id = ev_resp.json()["evidence_id"]

    act_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": "UPLOAD_INCOME_PROOF",
            "expected_snapshot_id": snap,
            "idempotency_key": str(uuid4()),
            "input": {"evidence_id": evidence_id},
        },
        headers=session_headers,
    )
    assert act_resp.status_code == 422, act_resp.text
    assert act_resp.json()["error"]["code"] == "EVIDENCE_CONFLICT"

    check_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    income_field = next(
        f for f in check_resp.json()["fields"] if f["key"] == "monthly_income"
    )
    assert income_field["value"] is None
    assert check_resp.json()["version_number"] == 1
