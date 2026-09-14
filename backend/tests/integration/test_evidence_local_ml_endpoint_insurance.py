"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
for INSURANCE with AI_PROVIDER=local_ml - proves the full wire contract
works for a non-Lending, boolean-target-field journey through the actual
multipart-upload path, not just the provider in isolation
(test_local_ml_provider_insurance.py already covers that layer).
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
from app.docai.dataset.generate_insurance import _degrade, _draw_discharge_summary, _make_fields
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(
        get_classifier("INSURANCE") is None, reason="No trained INSURANCE classifier present."
    ),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


def _generate_discharge_summary_jpeg(seed: int) -> bytes:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    fields = _make_fields(rng, fake, "MEDICAL_DISCHARGE_SUMMARY")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_discharge_summary(c, fields, "discharge_formal")
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)
    return img_buf.getvalue()


async def test_real_medical_document_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "INSURANCE",
        "goal": {"sum_insured": 1000000, "policy_type": "INDIVIDUAL"},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_discharge_summary_jpeg(seed=777)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "MEDICAL_DISCHARGE_SUMMARY", "expected_snapshot_id": snapshot_id},
        files={"file": ("discharge_summary.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    # NOTE on `verified`: `EvidenceReconciliationService` (pre-existing,
    # unchanged this phase) additionally gates `verified` on the
    # manifest's own per-doc_type `confidence_threshold` (0.85 for
    # MEDICAL_DISCHARGE_SUMMARY) - and a real classifier's honest
    # confidence (this pipeline's `compose_confidence`, a product of OCR
    # confidence x classification probability) routinely lands below that
    # threshold even for a genuinely correct document, because the
    # threshold values in every manifest were set against MockAI's old
    # confidence formula (`min(0.98, threshold + 0.07)` - deliberately
    # ALWAYS just above its own threshold by construction), not against a
    # real model's honest uncertainty. This is a real, disclosed,
    # cross-journey finding (confirmed to reproduce on LENDING too, not
    # something specific to Insurance) - not fixed this phase, since
    # "fixing" it by inflating confidence would violate the
    # never-fabricate-confidence rule; see docs/docai_insurance_report.md.
    # The correct, current, honest behavior this test asserts: the
    # document is genuinely recognized and its boolean field extracted
    # (not fabricated, not silently trusted past the threshold), and the
    # journey safely falls back to requiring review rather than a wrong
    # auto-accept.
    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "ped_declaration_submitted" in detected_keys
    assert "monthly_income" not in detected_keys
    assert "employer_name" not in detected_keys
    assert body["requires_review"] is True
    assert body["interpretation"]["confidence"] > 0.0
    # Expected Outcome (consequence_preview) is computed regardless of AI
    # confidence - it's purely deterministic, never gated by the
    # confidence/review status above.
    assert body["consequence_preview"] is not None


async def test_wrong_document_upload_through_http_endpoint_is_flagged_for_insurance(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "INSURANCE",
        "goal": {"sum_insured": 1000000, "policy_type": "INDIVIDUAL"},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    blank = Image.new("RGB", (800, 1100), color=(255, 255, 255))
    buf = io.BytesIO()
    blank.save(buf, format="JPEG", quality=70)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "MEDICAL_DISCHARGE_SUMMARY", "expected_snapshot_id": snapshot_id},
        files={"file": ("blank.jpg", buf.getvalue(), "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["interpretation"]["verified"] is False
    assert body["interpretation"]["detected"] == []
