"""Security/integrity regression suite for the Document AI integration
integrity fix (docs/docai_e2e_integration_fix_report.md). Covers every
case Part 6/13 of that phase's instructions explicitly enumerate, beyond
the two "wrong document" scenarios already covered in
test_docai_e2e_journeys.py.
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
    pytest.mark.skipif(get_classifier("LENDING") is None, reason="No trained classifier."),
    pytest.mark.asyncio,
]


def _generate_jpeg(draw_fn, fields, template, seed):
    rng = random.Random(seed)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    pil_img, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    pil_img.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


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


async def _upload_real_salary_slip(client: AsyncClient, headers: dict, journey_id, snap, seed):
    from app.docai.dataset.generate import _draw_salary_slip, _make_fields

    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")
    image_bytes = _generate_jpeg(_draw_salary_slip, fields, "salary_table", seed + 1)

    resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snap},
        files={"file": ("salary.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json(), fields


async def _exec(client, headers, journey_id, snap, action_id, action_input):
    return await client.post(
        f"/api/v1/journeys/{journey_id}/actions",
        json={
            "action_id": action_id,
            "expected_snapshot_id": snap,
            "idempotency_key": str(uuid4()),
            "input": action_input,
        },
        headers=headers,
    )


async def test_cross_journey_evidence_fails_safely(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Evidence uploaded for Journey A must not satisfy an action on
    Journey B, even within the SAME session."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_a, snap_a = await _create_lending_journey(client, session_headers)
    ev, _fields = await _upload_real_salary_slip(client, session_headers, journey_a, snap_a, 9101)

    journey_b, snap_b = await _create_lending_journey(client, session_headers)

    resp = await _exec(
        client,
        session_headers,
        journey_b,
        snap_b,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": ev["evidence_id"]},
    )
    assert resp.status_code == 404


async def test_cross_session_evidence_fails_safely(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Evidence uploaded under Session A must not be usable to satisfy an
    action on a DIFFERENT session's journey, even one of the SAME
    journey_type."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_a, snap_a = await _create_lending_journey(client, session_headers)
    ev, _fields = await _upload_real_salary_slip(client, session_headers, journey_a, snap_a, 9102)

    other_session_resp = await client.get("/api/v1/session")
    other_headers = {"X-Session-Id": other_session_resp.json()["session_id"]}
    journey_b, snap_b = await _create_lending_journey(client, other_headers)

    resp = await _exec(
        client,
        other_headers,
        journey_b,
        snap_b,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": ev["evidence_id"]},
    )
    assert resp.status_code == 404


async def test_unknown_evidence_id_fails_safely(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    resp = await _exec(
        client,
        session_headers,
        journey_id,
        snap,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": str(uuid4())},
    )
    assert resp.status_code == 404


async def test_malformed_evidence_id_fails_safely(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    resp = await _exec(
        client,
        session_headers,
        journey_id,
        snap,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": "not-a-uuid-at-all"},
    )
    assert resp.status_code == 404


async def test_evidence_action_mismatch_fails_safely(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Evidence genuinely verified for ONE action's doc_type must not
    satisfy a DIFFERENT action whose `accepts` doesn't include it (real
    manifest fact: `UPLOAD_INCOME_PROOF` accepts SALARY_SLIP/BANK_
    STATEMENT; `UPLOAD_WORK_ID` accepts OFFICE_ID_CARD - genuinely
    different doc_types)."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    ev, _fields = await _upload_real_salary_slip(client, session_headers, journey_id, snap, 9103)

    resp = await _exec(
        client,
        session_headers,
        journey_id,
        snap,
        "UPLOAD_WORK_ID",
        {"evidence_id": ev["evidence_id"]},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EVIDENCE_CONFLICT"


async def test_client_forged_field_value_is_ignored(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """A client sending a forged direct field value ALONGSIDE a real,
    valid evidence_id must have that forged value ignored - only the
    server-validated evidence result is ever consumed."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    ev, fields = await _upload_real_salary_slip(client, session_headers, journey_id, snap, 9104)

    forged_amount = 999999999
    assert forged_amount != fields["net_amt"]

    resp = await _exec(
        client,
        session_headers,
        journey_id,
        snap,
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": ev["evidence_id"], "monthly_income": forged_amount, "verified": True},
    )
    assert resp.status_code == 200, resp.text
    income_field = next(f for f in resp.json()["journey"]["fields"] if f["key"] == "monthly_income")
    assert income_field["value"] == fields["net_amt"]
    assert income_field["value"] != forged_amount


async def test_repeated_identical_action_remains_idempotent(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    ev, _fields = await _upload_real_salary_slip(client, session_headers, journey_id, snap, 9105)

    idem_key = str(uuid4())
    payload = {
        "action_id": "UPLOAD_INCOME_PROOF",
        "expected_snapshot_id": snap,
        "idempotency_key": idem_key,
        "input": {"evidence_id": ev["evidence_id"]},
    }
    resp1 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions", json=payload, headers=session_headers
    )
    resp2 = await client.post(
        f"/api/v1/journeys/{journey_id}/actions", json=payload, headers=session_headers
    )
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
    assert resp2.json()["journey"]["version_number"] == 2  # no duplicate snapshot


async def test_stale_snapshot_still_returns_409_with_real_evidence(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    ev, _fields = await _upload_real_salary_slip(client, session_headers, journey_id, snap, 9106)

    resp = await _exec(
        client,
        session_headers,
        journey_id,
        str(uuid4()),
        "UPLOAD_INCOME_PROOF",
        {"evidence_id": ev["evidence_id"]},
    )
    assert resp.status_code == 409


async def test_invalid_action_still_returns_422(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    resp = await _exec(client, session_headers, journey_id, snap, "NOT_A_REAL_ACTION", {})
    assert resp.status_code == 422


async def test_form_action_without_evidence_unaffected_by_fix(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """FORM actions (no evidence_id involved at all) keep using
    `action_input` exactly as before - this fix only changes EVIDENCE-
    kind actions that carry a real `evidence_id`."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    journey_id, snap = await _create_lending_journey(client, session_headers)
    resp = await _exec(
        client,
        session_headers,
        journey_id,
        snap,
        "SUBMIT_EMPLOYMENT_INFO",
        {"employment_type": "SALARIED"},
    )
    assert resp.status_code == 200, resp.text
    employment_field = next(
        f for f in resp.json()["journey"]["fields"] if f["key"] == "employment_type"
    )
    assert employment_field["value"] == "SALARIED"
