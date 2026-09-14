"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
for ACCOUNT_OPENING with AI_PROVIDER=local_ml - proves the full wire
contract works for the fifth journey through the actual multipart-upload
path, and specifically verifies the fixed `accepts` manifest bug (§9.2 of
the Insurance phase - same class of bug found a fourth time in Account
Opening's own manifest) produces a real, non-null consequence_preview for
SIGNATURE_SPECIMEN.

Also covers the manifest-integrity phase's findings on this journey's
remaining two evidence_mappings quirks:

- `upload_digital_signature.accepts` was `["image/png"]`, a genuine
  MIME-type-instead-of-doc_type defect - confirmed unambiguous by the
  frozen contract (`accepts` is documented as "Allowed doc_type values
  for EVIDENCE actions", no exception) AND by the frontend
  (`Screen06UploadEvidence.tsx` reads `action.accepts[0]` directly as the
  doc_type to submit - `image/png` would never have worked). The only
  evidence_mappings entry referencing this action_id is AADHAAR_FRONT_BACK,
  whose target_field already matches this action's own `satisfies` -
  fixed to `accepts: [AADHAAR_FRONT_BACK]`, verified below.
- `PAN_CARD_IMAGE`'s evidence_mappings entry still references an
  action_id (`upload_wet_signature`) whose `satisfies` doesn't match its
  own `target_field` - genuinely ambiguous (the only action that DOES
  satisfy `pan_authenticated`, `verify_pan_for_banking`, is a FORM with
  no document-intake path at all; repointing this would mean converting
  a manual-entry FORM into a document-upload EVIDENCE action, which is
  inventing business intent, not a mechanical fix) - left unchanged,
  verified to still fail predictably below.
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
from app.docai.dataset.generate_account_opening import (
    _draw_aadhaar,
    _draw_pan_card,
    _draw_signature_specimen,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(
        get_classifier("ACCOUNT_OPENING") is None,
        reason="No trained ACCOUNT_OPENING classifier present.",
    ),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_jpeg(draw_fn, doc_type: str, template: str, seed: int) -> bytes:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, doc_type)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


async def test_real_signature_specimen_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "ACCOUNT_OPENING", "goal": {"account_type": "DIGITAL_SAVINGS"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(
        _draw_signature_specimen, "SIGNATURE_SPECIMEN", "signature_card", seed=5001
    )

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "SIGNATURE_SPECIMEN", "expected_snapshot_id": snapshot_id},
        files={"file": ("signature.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "signature_uploaded" in detected_keys
    assert "pan_authenticated" not in detected_keys
    assert "ovd_document_uploaded" not in detected_keys
    # The manifest `accepts` fix (doc_type values, not MIME types) must
    # produce a real, non-null Expected Outcome - the same class of bug
    # that silently broke this for Insurance/KYC/Credit Card until traced
    # and fixed.
    assert body["consequence_preview"] is not None


async def test_pan_card_image_ai_fact_correct_but_consequence_preview_stays_null(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Documents the disclosed, NOT-fixed manifest routing gap: the AI
    layer correctly determines pan_authenticated=True (visible in
    `interpretation.detected`), but no action's `accepts` can correctly
    route a PAN_CARD_IMAGE upload (its evidence_mappings action_id points
    to `upload_wet_signature`, whose `satisfies` is signature_uploaded,
    not pan_authenticated) - fixing this would mean guessing which action
    was intended or inventing a new one, both out of scope this phase."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "ACCOUNT_OPENING", "goal": {"account_type": "DIGITAL_SAVINGS"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(_draw_pan_card, "PAN_CARD_IMAGE", "pan_standard", seed=5002)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "PAN_CARD_IMAGE", "expected_snapshot_id": snapshot_id},
        files={"file": ("pan.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "pan_authenticated" in detected_keys
    assert body["proposed_action_id"] is None
    assert body["consequence_preview"] is None


async def test_aadhaar_front_back_now_routes_correctly_after_accepts_fix(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Regression coverage for the manifest-integrity phase's fix:
    `upload_digital_signature.accepts` was `["image/png"]` (a MIME type,
    not a doc_type) - now `["AADHAAR_FRONT_BACK"]`, so an AADHAAR_FRONT_BACK
    upload must produce a real, non-null proposed_action_id/
    consequence_preview, unlike PAN_CARD_IMAGE's still-unresolved case
    above."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {"journey_type": "ACCOUNT_OPENING", "goal": {"account_type": "DIGITAL_SAVINGS"}}
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(_draw_aadhaar, "AADHAAR_FRONT_BACK", "aadhaar_standard", seed=5003)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "AADHAAR_FRONT_BACK", "expected_snapshot_id": snapshot_id},
        files={"file": ("aadhaar.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "signature_uploaded" in detected_keys
    assert body["proposed_action_id"] == "upload_digital_signature"
    assert body["consequence_preview"] is not None
