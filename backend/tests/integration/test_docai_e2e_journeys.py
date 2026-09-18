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
        client,
        session_headers,
        journey_id,
        snap,
        "submit_medical_declaration",
        {"has_medical_history": "NO"},
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
        client,
        session_headers,
        journey_id,
        snap,
        "verify_pan_for_banking",
        {"pan_number": "ABCDE1234F"},
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
    # Real-user QA regression: a wrong/unverified document must not produce
    # a confident "here's what will happen" preview either - before this
    # fix, `consequence_preview`/`diff_preview` were computed unconditionally
    # from manifest.simulation_defaults whenever the evidence's doc_type
    # nominally matched an action's `accepts`, regardless of whether the AI
    # actually verified it. Found via a real browser session against the
    # live backend, not by static inspection.
    assert ev["consequence_preview"] is None
    assert ev["diff_preview"] is None
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
    # Real-user QA regression: a wrong/unverified document must not produce
    # a confident "here's what will happen" preview either - before this
    # fix, `consequence_preview`/`diff_preview` were computed unconditionally
    # from manifest.simulation_defaults whenever the evidence's doc_type
    # nominally matched an action's `accepts`, regardless of whether the AI
    # actually verified it. Found via a real browser session against the
    # live backend, not by static inspection.
    assert ev["consequence_preview"] is None
    assert ev["diff_preview"] is None
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


async def test_genuine_unrelated_pdf_is_not_shown_as_verified_salary_slip(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Real-user-reported regression (BUG-001 in docs/
    paytmflow_final_full_flow_audit.md): a real user uploaded a genuine,
    unrelated presentation-style PDF (a hackathon slide deck, containing no
    salary-slip vocabulary at all) where a SALARY_SLIP was expected, and the
    then-running server showed it as `verified`/`92% confidence`/`₹85,000
    Monthly Net Income` - the exact manifest `simulation_defaults` value.
    Root cause (confirmed): the server the user tested against was actually
    running `AI_PROVIDER=mock` (MockAI is a DELIBERATE, documented, fixed-
    output stub for frontend dev with no real document analysis at all -
    see app/ai/mock.py's own docstring), not the real `local_ml` pipeline.
    This test proves the REAL pipeline (`AI_PROVIDER=local_ml`, explicitly
    set here exactly as every other test in this file does) correctly
    refuses to fabricate a verified result for a genuinely unrelated,
    low-text PDF - reproducing the user's exact document shape (a title +
    a handful of short unrelated lines, no salary-slip labels), not a
    synthetic OTHER-class receipt like the other wrong-document tests in
    this file."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, h - 60, "FIN-SHIELD")
    c.setFont("Helvetica", 14)
    c.drawCentredString(w / 2, h - 90, "Hackathon Presentation")
    c.setFont("Helvetica", 11)
    for i, line in enumerate(
        [
            "Team: Alpha Squad",
            "Problem Statement: Financial fraud detection at scale",
            "Solution Architecture: Real-time anomaly detection pipeline",
            "Tech Stack: Python, Kafka, PostgreSQL, React",
            "Demo Roadmap: Q1 - Q4 milestones",
            "Thank you for your attention!",
        ]
    ):
        c.drawString(60, h - 140 - i * 24, line)
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={
            "file": (
                "FIN-SHIELD_Hackathon_Presentation.pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert resp.status_code == 200, resp.text
    ev = resp.json()

    # The exact runtime fields a real user (and Screen 7) sees.
    assert ev["interpretation"]["verified"] is False
    assert ev["interpretation"]["detected"] == []
    assert "85,000" not in ev["interpretation"]["summary"]
    assert "85000" not in ev["interpretation"]["summary"]
    # No fabricated "here's what will happen" preview either (the same
    # `evidence_is_genuine` gate fixed in the prior P1 phase, re-confirmed
    # here for the AMBIGUOUS/UNREADABLE outcome path specifically, not just
    # the WRONG_DOCUMENT path the other tests in this file exercise).
    assert ev["consequence_preview"] is None
    assert ev["diff_preview"] is None

    # And confirm no state was mutated by merely uploading it (POST
    # /evidence is preview-only, unchanged architectural invariant).
    check = await client.get(f"/api/v1/journeys/{journey_id}", headers=session_headers)
    income_field = next(f for f in check.json()["fields"] if f["key"] == "monthly_income")
    assert income_field["value"] is None
    assert check.json()["version_number"] == 1


async def test_alternate_accepted_doc_type_is_not_falsely_rejected(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Human-first real-browser QA regression (BUG-005 in docs/
    paytmflow_human_first_final_qa.md): UPLOAD_INCOME_PROOF accepts EITHER
    SALARY_SLIP or BANK_STATEMENT (two real, independently-thresholded
    evidence_mappings entries in lending.yaml, same action_id, same
    target_field) - but the frontend always declares `doc_type` as
    `action.accepts[0]` ("SALARY_SLIP") when uploading, since it has no
    way to know in advance which of the two accepted types the user's real
    file actually is. Before this fix, a genuine BANK_STATEMENT (the
    SECOND accepted type) uploaded this way was always flagged
    WRONG_DOCUMENT ("This does not look like the expected Salary Slip")
    purely because of its position in the manifest's accepts list, not
    because of anything wrong with the document. Reproduced here exactly
    as the real frontend does: upload a genuine BANK_STATEMENT image while
    declaring doc_type=SALARY_SLIP."""
    from app.docai.dataset.generate import _draw_bank_statement, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    rng = random.Random(9301)
    fake = Faker()
    Faker.seed(9301)
    fields = _make_fields(rng, fake, "BANK_STATEMENT", "symbol")
    image_bytes = _generate_jpeg(_draw_bank_statement, fields, "bank_hdfc", 9302)

    # Declares SALARY_SLIP (accepts[0]) - exactly what the real frontend
    # does today, regardless of which accepted type the file actually is.
    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )

    # NOT rejected as a wrong document - the core of this regression. Wire-
    # level `verified` may still be False purely from the same, separate,
    # already-disclosed confidence-threshold-vs-genuine-correctness gap
    # every other real-document test in this session hits (composed
    # confidence often lands below the manifest threshold even for
    # genuinely correct documents) - that is NOT what this test is about.
    # The summary text itself is one of two genuine, real strings depending
    # on whether THIS run's composed confidence cleared the manifest
    # threshold: the plain local_ml.py extraction summary, or (below
    # threshold) reconcile.py's CASE A explanation (see
    # test_genuinely_recognized_document_below_confidence_threshold_
    # explains_review) - both mention the real recognized doc_type and
    # neither ever says the document doesn't look like what was expected.
    summary = ev["interpretation"]["summary"]
    assert "does not look like the expected" not in summary
    assert "bank statement" in summary.lower()
    assert "recognized" in summary.lower()
    assert ev["interpretation"]["detected"], "alternate accepted doc_type must not be rejected"
    detected_keys = {d["key"] for d in ev["interpretation"]["detected"]}
    assert "monthly_income" in detected_keys

    # And executing the resulting action must use the REAL extracted value
    # (whatever the local OCR/extraction pipeline genuinely read from this
    # document - decoupled here from ground truth, since OCR-quality
    # variance on a randomly-degraded synthetic image is a separate,
    # already-covered-elsewhere concern; this test is about the routing/
    # acceptance fix, not extraction accuracy), never the manifest's
    # simulation_defaults constant (85000) or the OTHER document's value.
    expected_display = next(
        d["display_value"] for d in ev["interpretation"]["detected"] if d["key"] == "monthly_income"
    )
    act = await _execute_action(
        client,
        session_headers,
        journey_id,
        snap,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": ev["evidence_id"]},
    )
    assert act.status_code == 200, act.text
    income_field = next(f for f in act.json()["journey"]["fields"] if f["key"] == "monthly_income")
    assert income_field["value"] is not None
    assert income_field["value"] != 85000
    assert f"₹{income_field['value']:,}" == expected_display


async def test_genuinely_wrong_document_still_rejected_when_action_accepts_multiple_types(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Regression-safety companion to the test above: fixing the false
    NEGATIVE for a genuinely-accepted alternate type must not turn into a
    false POSITIVE - a document that is neither SALARY_SLIP nor
    BANK_STATEMENT must still be correctly rejected for
    UPLOAD_INCOME_PROOF."""
    from app.docai.dataset.generate import _draw_other, _make_fields

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    rng = random.Random(9303)
    fake = Faker()
    Faker.seed(9303)
    fields = _make_fields(rng, fake, "OTHER", "symbol")
    image_bytes = _generate_jpeg(_draw_other, fields, "receipt", 9304)

    ev = await _upload_evidence(
        client, session_headers, journey_id, snap, "SALARY_SLIP", image_bytes
    )
    assert ev["interpretation"]["verified"] is False
    assert ev["interpretation"]["detected"] == []
    assert ev["consequence_preview"] is None


async def test_native_text_pdf_with_label_value_in_table_columns_is_extracted(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Human-real-user QA regression (BUG-008): a real, genuine, born-
    digital PDF (not rasterized/OCR'd - a real PyMuPDF text layer) laying
    its income label and value out as two side-by-side table cells on the
    same printed row, uploaded through the REAL HTTP evidence endpoint
    exactly as a real user did. Before the fix, `extract_pdf_text_layer()`
    never populated per-line position data at all, so this genuinely
    correct document's income value could not be extracted -
    "Recognized this as a Salary Slip, but could not reliably extract the
    required value from it." Reproduces the real user-reported document's
    LAYOUT PATTERN generically (any label/value pair in table columns),
    not the literal file."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, h - 60, "MONTHLY SALARY SLIP")
    # Real salary slips carry an employer header and pay-period line above
    # the field/value table - added so this fixture has the same genuine
    # salary-slip vocabulary a real document would, rather than being just
    # a bare 2-row table (which was already only marginally above the
    # classifier's confidence floor even before the cross-journey "OTHER"
    # training fix below, at 0.489 - this is the classification signal a
    # real such document actually carries, not a change to what's under
    # test: the row-band table-column extraction mechanism itself, which
    # is still exactly the same two-column "Field"/"Value" layout.
    c.setFont("Helvetica", 9)
    c.drawString(60, h - 78, "Acme Technologies Pvt Ltd")
    c.drawString(60, h - 90, "Payslip for the month of March 2026")
    c.setFont("Helvetica", 10)
    c.drawString(60, h - 100, "Field")
    c.drawString(300, h - 100, "Value")
    c.drawString(60, h - 130, "Document Type")
    c.drawString(300, h - 130, "SALARY_SLIP")
    c.drawString(60, h - 160, "Monthly Net Income")
    c.drawString(300, h - 160, "1,42,000 INR")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={
            "file": (
                "salary_slip_table_layout.pdf",
                pdf_bytes,
                "application/pdf",
            )
        },
        headers=session_headers,
    )
    assert resp.status_code == 200, resp.text
    ev = resp.json()

    assert ev["interpretation"]["detected"], "table-layout label/value must be extracted"
    detected_keys = {d["key"] for d in ev["interpretation"]["detected"]}
    assert "monthly_income" in detected_keys
    income_display = next(
        d["display_value"] for d in ev["interpretation"]["detected"] if d["key"] == "monthly_income"
    )
    assert "142,000" in income_display
    assert "could not reliably extract" not in ev["interpretation"]["summary"]


async def test_genuinely_recognized_document_below_confidence_threshold_explains_review(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Human-real-user QA regression (CASE A / confidence-threshold UX): a
    real user uploaded their own real salary slip PDF and got "Review
    Needed" with a summary saying "...confidence 73%.". Traced live: the
    document WAS correctly classified as SALARY_SLIP (CORRECT_DOCUMENT),
    the income value WAS correctly extracted and passed validation
    (133000, no conflicts), but composed confidence (ocr_confidence *
    classification_confidence, since field_found+validated -> no penalty)
    landed below SALARY_SLIP's manifest threshold (0.85) - a legitimate,
    NOT-a-bug review-routing decision. The bugs were in the UX/copy: (1)
    the summary text exposed a raw confidence percentage, violating
    frontend/CLAUDE.md rule 1 ("never render a percentage") - confirmed
    live on this exact document; (2) the review reason was not
    distinguishable from a genuinely wrong/unreadable document.

    This test reproduces the SAME real scenario generically: a minimal,
    sparse two-column-layout PDF (built with reportlab, not the user's
    literal file) that the real trained classifier - unmodified, no
    threshold change - genuinely scores below the real SALARY_SLIP
    threshold precisely because it is sparse (little text for the
    classifier to work with), while extraction still succeeds and
    validates for real. This is a real, live, below-threshold document,
    not a mocked one.
    """
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_journey(
        client,
        session_headers,
        "LENDING",
        {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, h - 60, "MONTHLY SALARY SLIP")
    c.setFont("Helvetica", 10)
    c.drawString(60, h - 100, "Field")
    c.drawString(300, h - 100, "Value")
    c.drawString(60, h - 130, "Document Type")
    c.drawString(300, h - 130, "SALARY_SLIP")
    c.drawString(60, h - 160, "Monthly Net Income")
    c.drawString(300, h - 160, "133,000 INR")
    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={"file": ("sparse_salary_slip.pdf", pdf_bytes, "application/pdf")},
        headers=session_headers,
    )
    assert resp.status_code == 200, resp.text
    ev = resp.json()

    interp = ev["interpretation"]
    # Real, below-threshold classification - the whole point of this test.
    assert 0.0 < interp["confidence"] < 0.85
    assert interp["conflicts"] == []
    assert interp["verified"] is False
    assert ev["requires_review"] is True

    # Extraction genuinely succeeded - the value itself is not in question.
    detected_keys = {d["key"] for d in interp["detected"]}
    assert "monthly_income" in detected_keys

    # CASE A UX fix: the summary must explain that the document WAS
    # recognized and extracted, and that review is a confidence routing
    # decision - not imply the extracted value is wrong - and must never
    # contain a raw percentage (frontend/CLAUDE.md rule 1).
    summary = interp["summary"]
    assert "%" not in summary
    assert "recognized" in summary.lower()
    assert "extracted successfully" in summary.lower()
    assert "not in question" in summary.lower()
    assert "could not reliably extract" not in summary

    # The deterministic preview must still reflect the real, genuine
    # extraction - a low-confidence-but-genuine document is not a wrong
    # document; consequence_preview must not be suppressed or fabricated.
    assert ev["consequence_preview"] is not None
    newly_satisfied_keys = {f["key"] for f in ev["consequence_preview"]["newly_satisfied"]}
    assert "monthly_income" in newly_satisfied_keys
