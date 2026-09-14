"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
with AI_PROVIDER=local_ml - proves the full wire contract (multipart file
upload -> storage -> real OCR -> real classification/extraction ->
EvidenceResponse) works, not just the provider in isolation.
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
from app.docai.dataset.generate import _degrade, _draw_salary_slip, _make_fields
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(
        get_classifier("LENDING") is None, reason="No trained LENDING classifier present."
    ),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_salary_slip_jpeg(seed: int) -> tuple[bytes, int]:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")

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
    return img_buf.getvalue(), fields["net_amt"]


async def test_real_document_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes, expected_income = _generate_salary_slip_jpeg(seed=555)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snapshot_id},
        files={"file": ("salary_slip.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    # The genuinely extracted value must be the REAL randomized amount
    # rendered onto this specific document - not the previously hardcoded
    # MockAI constant (85000) - proving the real pipeline is wired end to
    # end through the actual HTTP contract, not just unit-level.
    # (EvidenceDetectedField's wire shape - app/schemas/evidence.py - only
    # exposes key/label/display_value, no raw numeric `value`, so the
    # formatted display string is what's checked here.)
    detected = {d["key"]: d["display_value"] for d in body["interpretation"]["detected"]}
    assert detected.get("monthly_income") == f"₹{expected_income:,}"


async def test_wrong_document_upload_through_http_endpoint_is_flagged(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "LENDING",
        "goal": {"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    # A blank white image - nothing to classify.
    blank = Image.new("RGB", (800, 1100), color=(255, 255, 255))
    buf = io.BytesIO()
    blank.save(buf, format="JPEG", quality=70)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SALARY_SLIP", "expected_snapshot_id": snapshot_id},
        files={"file": ("blank.jpg", buf.getvalue(), "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["interpretation"]["verified"] is False
    assert body["interpretation"]["detected"] == []
