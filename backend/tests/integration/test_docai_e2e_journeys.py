"""End-to-end proof, for all six journeys, that the REAL local Document AI
path (AI_PROVIDER=local_ml) is correctly wired all the way through the
actual production HTTP surface:

    create journey -> upload REAL rendered evidence -> OCR -> classify ->
    extract -> normalize/validate -> consistency -> execute the resulting
    action -> snapshot advances -> recommendation endpoint reflects the
    new state.

Scope decision (E2E + performance phase): this file proves the ONE thing
the six journeys' existing per-doc-type test files
(test_evidence_local_ml_endpoint_*.py) do NOT already prove - that a real
AI-detected/verified evidence submission actually flows through
POST /journeys/{id}/actions and produces a real, persisted snapshot
version bump and a recommendation-endpoint reflection of it. Driving
every journey all the way to READY through every remaining FORM action
would only re-prove the deterministic engine's own action-sequencing
logic, which `test_full_journey_flow.py::test_lending_golden_path_end_to_
end_integration` (unchanged, still passing) and each journey's own
`test_*_dag_structure` test already cover - not re-duplicated here.
"""

import io
import random
from uuid import uuid4

import pymupdf
import pytest
from faker import Faker
from httpx import AsyncClient
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.config import settings
from app.docai.classifier import get_classifier
from app.docai.dataset.generate import _degrade
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_jpeg(draw_fn, fields, template, seed, quality=85, degrade=True):
    rng = random.Random(seed)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    if degrade:
        pil_img, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    pil_img.save(img_buf, format="JPEG", quality=quality)
    return img_buf.getvalue()


async def _create_journey(client: AsyncClient, headers: dict, journey_type: str, goal: dict):
    resp = await client.post(
        "/api/v1/journeys",
        json={"journey_type": journey_type, "goal": goal},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["journey_id"], body["snapshot_id"]


async def _upload_evidence(client, headers, journey_id, snapshot_id, doc_type, image_bytes):
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": doc_type, "expected_snapshot_id": snapshot_id},
        files={"file": (f"{doc_type.lower()}.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _execute_action(client, headers, journey_id, snapshot_id, action_id, action_input=None):
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": action_id,
            "expected_snapshot_id": snapshot_id,
            "idempotency_key": str(uuid4()),
            "input": action_input or {},
        },
        headers=headers,
    )
    return resp


@pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier.")
async def test_lending_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """HAPPY-PATH REGRESSION for the Document AI integration integrity
    fix. Deliberately uses a real income figure (₹208,000) that does NOT
    match the manifest's `simulation_defaults` value (₹85,000), so a
    passing assertion here can only mean the real extracted value was
    genuinely consumed - not a coincidental match."""
    from app.docai.dataset.generate import _draw_salary_slip, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    rng = random.Random(7001)
    fake = Faker()
    Faker.seed(7001)
    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
    assert fields["net_amt"] != 85000  # sanity: fixture must differ from simulation_defaults
    image_bytes = _generate_jpeg(_draw_salary_slip, fields, "salary_table", 7002)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )
    assert ev["interpretation"]["verified"] is True or ev["consequence_preview"] is not None
    detected_keys = {d["key"] for d in ev["interpretation"]["detected"]}
    assert "monthly_income" in detected_keys
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id == "UPLOAD_INCOME_PROOF"

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    new_journey = act.json()["journey"]
    assert new_journey["version_number"] == 2

    # The deterministic engine's PERSISTED value must be the real,
    # extracted figure - not the manifest's simulation_defaults constant.
    income_field = next(f for f in new_journey["fields"] if f["key"] == "monthly_income")
    assert income_field["value"] == fields["net_amt"]
    assert income_field["value"] != 85000

    rec_resp = await client.get(
        f"/api/v1/journeys/{journey_id}/recommendation", headers=session_headers
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["snapshot_id"] == new_journey["snapshot_id"]


@pytest.mark.skipif(get_classifier("INSURANCE") is None, reason="No trained classifier.")
async def test_insurance_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate_insurance import _draw_health_checkup, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "INSURANCE",
        {"policy_type": "INDIVIDUAL", "sum_insured": 500000},
    )

    # submit_ped_records' own precondition (medical_history_declared)
    # must be satisfied first - a real manifest fact, not a test
    # artifact.
    med_act = await _execute_action(
        client, session_headers, journey_id, snap, "submit_medical_declaration", {}
    )
    assert med_act.status_code == 200, med_act.text
    snap = med_act.json()["journey"]["snapshot_id"]

    rng = random.Random(7003)
    fake = Faker()
    Faker.seed(7003)
    fields = _make_fields(rng, fake, "HEALTH_CHECKUP_REPORT")
    image_bytes = _generate_jpeg(_draw_health_checkup, fields, "checkup_table", 7004)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "HEALTH_CHECKUP_REPORT", image_bytes
    )
    detected_keys = {d["key"] for d in ev["interpretation"]["detected"]}
    assert "ped_declaration_submitted" in detected_keys
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id is not None

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    assert act.json()["journey"]["version_number"] == 3


@pytest.mark.skipif(get_classifier("KYC") is None, reason="No trained classifier.")
async def test_kyc_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate_kyc import _draw_passport, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client, session_headers, "KYC", {"kyc_purpose": "PERIODIC_UPDATE"}
    )

    rng = random.Random(7005)
    fake = Faker()
    Faker.seed(7005)
    fields = _make_fields(rng, fake, "PASSPORT_SCAN")
    image_bytes = _generate_jpeg(_draw_passport, fields, "passport_biopage", 7006)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "PASSPORT_SCAN", image_bytes
    )
    assert "ovd_document_uploaded" in {d["key"] for d in ev["interpretation"]["detected"]}
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id is not None

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    assert act.json()["journey"]["version_number"] == 2


@pytest.mark.skipif(get_classifier("CREDIT_CARD") is None, reason="No trained classifier.")
async def test_credit_card_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate_credit_card import _draw_salary_slip, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client, session_headers, "CREDIT_CARD", {"card_variant": "CASHBACK"}
    )

    rng = random.Random(7007)
    fake = Faker()
    Faker.seed(7007)
    fields = _make_fields(rng, fake, "SALARY_SLIP")
    image_bytes = _generate_jpeg(_draw_salary_slip, fields, "salary_table", 7008)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )
    assert "income_verified" in {d["key"] for d in ev["interpretation"]["detected"]}
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id == "upload_salary_statement"

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    assert act.json()["journey"]["version_number"] == 2


@pytest.mark.skipif(get_classifier("ACCOUNT_OPENING") is None, reason="No trained classifier.")
async def test_account_opening_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate_account_opening import _draw_signature_specimen, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client, session_headers, "ACCOUNT_OPENING", {"account_type": "DIGITAL_SAVINGS"}
    )

    # upload_wet_signature's own precondition (pan_authenticated) must be
    # satisfied first - a real manifest fact (identity_verified is
    # SATISFIED by default, but pan_authenticated is not), not an
    # artifact of this test.
    pan_act = await _execute_action(
        client, session_headers, journey_id, snap, "verify_pan_for_banking", {}
    )
    assert pan_act.status_code == 200, pan_act.text
    snap = pan_act.json()["journey"]["snapshot_id"]

    rng = random.Random(7009)
    fake = Faker()
    Faker.seed(7009)
    fields = _make_fields(rng, fake, "SIGNATURE_SPECIMEN")
    image_bytes = _generate_jpeg(_draw_signature_specimen, fields, "signature_card", 7010)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SIGNATURE_SPECIMEN", image_bytes
    )
    assert "signature_uploaded" in {d["key"] for d in ev["interpretation"]["detected"]}
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id == "upload_wet_signature"

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    assert act.json()["journey"]["version_number"] == 3


@pytest.mark.skipif(get_classifier("INVESTMENT") is None, reason="No trained classifier.")
async def test_investment_e2e_real_evidence_advances_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate_investment import _draw_cancelled_cheque, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "INVESTMENT",
        {"investment_mode": "MONTHLY_SIP", "target_amount": 5000},
    )

    rng = random.Random(7011)
    fake = Faker()
    Faker.seed(7011)
    fields = _make_fields(rng, fake, "CANCELLED_CHEQUE")
    image_bytes = _generate_jpeg(_draw_cancelled_cheque, fields, "cheque_standard", 7012)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "CANCELLED_CHEQUE", image_bytes
    )
    assert "bank_account_verified" in {d["key"] for d in ev["interpretation"]["detected"]}
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id == "upload_cancelled_cheque"

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    assert act.json()["journey"]["version_number"] == 2


# --- Failure-path proofs (wrong doc, degraded doc, stale snapshot) ---


@pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier.")
async def test_wrong_document_does_not_advance_lending_state(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """CRITICAL REGRESSION CASE for the Document AI integration integrity
    fix (docs/docai_e2e_integration_fix_report.md) - reproduces the exact
    P1 scenario found during the E2E + performance phase, now proving it
    is fixed: a genuine wrong document is correctly flagged invalid by
    the real local Document AI pipeline, and executing the resulting
    action EXACTLY as the real frontend does
    (`{"evidence_id": "<real evidence id>"}`, nothing else) must NOT set
    `monthly_income` to the manifest's `simulation_defaults` value
    (₹85,000) or any other fabricated number, and must NOT falsely mark
    the income evidence as satisfied. Before the fix, this exact
    sequence produced `monthly_income=85000`, HTTP 200 - see the E2E
    report §10 for that finding.
    """
    from app.docai.dataset.generate import _draw_other, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    rng = random.Random(7013)
    fake = Faker()
    Faker.seed(7013)
    fields = _make_fields(rng, fake, "OTHER", "symbol")
    image_bytes = _generate_jpeg(_draw_other, fields, "receipt", 7014)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )
    assert ev["interpretation"]["verified"] is False
    assert ev["interpretation"]["detected"] == []
    proposed_action_id = ev["proposed_action_id"]

    # Confirm the deterministic snapshot genuinely did not change from
    # the upload alone (evidence upload never mutates state by itself).
    snap_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    assert snap_resp.status_code == 200
    assert snap_resp.json()["version_number"] == 1

    # Execute the action EXACTLY as the real frontend does - only the
    # evidence reference, never the extracted value itself.
    if proposed_action_id:
        act = await _execute_action(
            client,
            session_headers,
            journey_id,
            snap_resp.json()["snapshot_id"],
            proposed_action_id,
            {"evidence_id": ev["evidence_id"]},
        )
        # FIXED: the backend resolves evidence_id server-side, finds it
        # was never verified (wrong document), and rejects the action
        # outright - no snapshot is created, no field is set, no
        # simulation_defaults value of any kind is ever consulted.
        assert act.status_code == 422
        body = act.json()
        assert body["error"]["code"] == "EVIDENCE_CONFLICT"

        # Confirm the snapshot STILL did not advance - the rejected
        # action attempt left no trace on journey state.
        final_snap_resp = await client.get(
            f"/api/v1/journeys/{journey_id}", headers=session_headers
        )
        assert final_snap_resp.json()["version_number"] == 1
        income_field = next(
            f for f in final_snap_resp.json()["fields"] if f["key"] == "monthly_income"
        )
        assert income_field["value"] is None, (
            "The income evidence requirement must not be falsely satisfied by a wrong document."
        )


@pytest.mark.skipif(get_classifier("CREDIT_CARD") is None, reason="No trained classifier.")
async def test_wrong_document_does_not_set_boolean_field_true_on_execution(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Same regression case as `test_wrong_document_does_not_advance_
    lending_state` above, confirmed for a BOOLEAN target field (5 of 6
    journeys' real evidence targets) instead of a MONEY one - before the
    fix, `deterministic_check.py`'s bare `else: True` fallback (no
    `simulation_defaults` entry needed) set `income_verified = True` for
    a wrong document too. Now correctly rejected."""
    from app.docai.dataset.generate_credit_card import _draw_other, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client, session_headers, "CREDIT_CARD", {"card_variant": "CASHBACK"}
    )

    rng = random.Random(7017)
    fake = Faker()
    Faker.seed(7017)
    fields = _make_fields(rng, fake, "OTHER")
    image_bytes = _generate_jpeg(_draw_other, fields, "receipt", 7018)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )
    assert ev["interpretation"]["verified"] is False
    assert ev["interpretation"]["detected"] == []
    proposed_action_id = ev["proposed_action_id"]
    assert proposed_action_id == "upload_salary_statement"

    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        proposed_action_id,
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 422
    assert act.json()["error"]["code"] == "EVIDENCE_CONFLICT"

    final_snap_resp = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    assert final_snap_resp.json()["version_number"] == 1
    income_verified_field = next(
        f for f in final_snap_resp.json()["fields"] if f["key"] == "income_verified"
    )
    assert income_verified_field["value"] is not True, (
        "The income_verified requirement must not be falsely satisfied by a wrong document."
    )


@pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier.")
async def test_stale_snapshot_returns_409_for_real_evidence_upload(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    from app.docai.dataset.generate import _draw_salary_slip, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, _snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    rng = random.Random(7015)
    fake = Faker()
    Faker.seed(7015)
    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
    image_bytes = _generate_jpeg(_draw_salary_slip, fields, "salary_table", 7016)

    fake_stale_snapshot = str(uuid4())
    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": fake_stale_snapshot},
        files={"file": ("salary.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert resp.status_code == 409


# Cross-session isolation for the evidence endpoint is already covered by
# `test_evidence_endpoints.py::test_upload_evidence_cross_session_404` -
# not duplicated here; this file's job is proving the REAL local-AI path
# specifically, not re-proving session isolation a second time.
