"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
for KYC with AI_PROVIDER=local_ml - proves the full wire contract works
for the third journey through the actual multipart-upload path, and
specifically verifies the fixed `accepts` manifest bug (§9.2 of the
Insurance phase - same class of bug found again in KYC's own manifest)
produces a real, non-null consequence_preview.
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
from app.docai.dataset.generate_kyc import _degrade, _draw_passport, _make_fields
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(get_classifier("KYC") is None, reason="No trained KYC classifier present."),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_passport_jpeg(seed: int) -> bytes:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, "PASSPORT_SCAN")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_passport(c, fields, "passport_biopage")
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


async def test_real_passport_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "KYC", "goal": {"kyc_purpose": "PERIODIC_UPDATE"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_passport_jpeg(seed=2001)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "PASSPORT_SCAN", "expected_snapshot_id": snapshot_id},
        files={"file": ("passport.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "ovd_document_uploaded" in detected_keys
    assert "monthly_income" not in detected_keys
    assert "ped_declaration_submitted" not in detected_keys
    # The manifest `accepts` fix (doc_type values, not MIME types) must
    # produce a real, non-null Expected Outcome - the same class of bug
    # that silently broke this for Insurance until traced and fixed.
    assert body["consequence_preview"] is not None


async def test_driving_licence_accepted_under_passport_action_per_manifest(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Real manifest fact, not assumed: DRIVING_LICENCE evidence maps to
    upload_passport_ovd's action_id, not a separate action - the endpoint
    must accept it under the SAME action as a passport."""
    from app.docai.dataset.generate_kyc import _draw_driving_licence

    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "KYC", "goal": {"kyc_purpose": "PERIODIC_UPDATE"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    rng = random.Random(2002)
    fake = Faker()
    Faker.seed(2002)
    fields = _make_fields(rng, fake, "DRIVING_LICENCE")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_driving_licence(c, fields, "dl_standard")
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
        data={"doc_type": "DRIVING_LICENCE", "expected_snapshot_id": snapshot_id},
        files={"file": ("dl.jpg", img_buf.getvalue(), "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["proposed_action_id"] == "upload_passport_ovd"
    assert body["consequence_preview"] is not None
