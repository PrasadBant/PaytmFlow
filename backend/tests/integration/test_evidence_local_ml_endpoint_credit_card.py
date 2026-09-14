"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
for CREDIT_CARD with AI_PROVIDER=local_ml - proves the full wire contract
works for the fourth journey through the actual multipart-upload path,
and specifically verifies the fixed `accepts` manifest bug (§9.2 of the
Insurance phase - same class of bug found a third time in Credit Card's
own manifest) produces a real, non-null consequence_preview.
"""

import io
import random

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
from app.docai.dataset.generate_credit_card import _draw_salary_slip, _make_fields
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(
        get_classifier("CREDIT_CARD") is None, reason="No trained CREDIT_CARD classifier present."
    ),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_salary_slip_jpeg(seed: int) -> bytes:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, "SALARY_SLIP")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_salary_slip(c, fields, "salary_table")
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


async def test_real_salary_slip_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "CREDIT_CARD", "goal": {"card_variant": "CASHBACK"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_salary_slip_jpeg(seed=3001)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snapshot_id},
        files={"file": ("salary_slip.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "income_verified" in detected_keys
    assert "ovd_document_uploaded" not in detected_keys
    assert "ped_declaration_submitted" not in detected_keys
    # The manifest `accepts` fix (doc_type values, not MIME types) must
    # produce a real, non-null Expected Outcome - the same class of bug
    # that silently broke this for Insurance/KYC until traced and fixed.
    assert body["consequence_preview"] is not None


async def test_it_return_accepted_under_its_own_alternate_action(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Real manifest fact, not assumed: ITR_V_ACKNOWLEDGEMENT maps to
    upload_it_return, a DIFFERENT action_id than SALARY_SLIP's
    upload_salary_statement, even though both satisfy income_verified."""
    from app.docai.dataset.generate_credit_card import _draw_itr

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "CREDIT_CARD", "goal": {"card_variant": "REWARDS"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    rng = random.Random(3002)
    fake = Faker()
    Faker.seed(3002)
    fields = _make_fields(rng, fake, "ITR_V_ACKNOWLEDGEMENT")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_itr(c, fields, "itr_formal")
    c.showPage()
    c.save()
    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "ITR_V_ACKNOWLEDGEMENT", "expected_snapshot_id": snapshot_id},
        files={"file": ("itr.jpg", img_buf.getvalue(), "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["proposed_action_id"] == "upload_it_return"
    assert body["consequence_preview"] is not None
