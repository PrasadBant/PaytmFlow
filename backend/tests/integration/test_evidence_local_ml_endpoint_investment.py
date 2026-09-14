"""End-to-end test of the real POST /journeys/{id}/evidence HTTP endpoint
for INVESTMENT with AI_PROVIDER=local_ml - proves the full wire contract
works for the sixth and final journey through the actual multipart-upload
path, and specifically verifies the fixed `accepts` manifest bug (§9.2 of
the Insurance phase - same class of bug found a fifth time in Investment's
own manifest) produces a real, non-null consequence_preview for BOTH
CANCELLED_CHEQUE and BANK_STATEMENT_SUMMARY (both correctly wired to the
same action_id per evidence_mappings).

Also documents, honestly, the DISCLOSED manifest defect this phase found
and did NOT fix: KRA_KYC_LETTER's evidence_mappings entry references
`action_id: upload_cancelled_cheque`, whose `satisfies` is
`bank_account_verified`, not `kra_kyc_validated` - so its
consequence_preview stays null at the HTTP layer even though the AI-level
boolean fact IS correctly determined (see
test_local_ml_provider_investment.py). Fixing this would require
inventing a new EVIDENCE action for `check_kra_status` (a FORM with no
document-intake path at all) or guessing manifest intent, both explicitly
out of scope this phase.
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
from app.docai.dataset.generate_investment import (
    _draw_bank_statement,
    _draw_cancelled_cheque,
    _draw_kra_letter,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE

pytestmark = [
    pytest.mark.skipif(
        get_classifier("INVESTMENT") is None,
        reason="No trained INVESTMENT classifier present.",
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


async def test_real_cancelled_cheque_upload_through_http_endpoint_with_local_ml(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "INVESTMENT",
        "goal": {"investment_mode": "MONTHLY_SIP", "target_amount": 5000},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    assert create_resp.status_code == 201
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(
        _draw_cancelled_cheque, "CANCELLED_CHEQUE", "cheque_standard", seed=10001
    )

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "CANCELLED_CHEQUE", "expected_snapshot_id": snapshot_id},
        files={"file": ("cheque.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "bank_account_verified" in detected_keys
    assert "kra_kyc_validated" not in detected_keys
    # The manifest `accepts` fix (doc_type values, not MIME types) must
    # produce a real, non-null Expected Outcome - the same class of bug
    # that silently broke this for every prior journey until traced and
    # fixed.
    assert body["consequence_preview"] is not None
    assert body["proposed_action_id"] == "upload_cancelled_cheque"


async def test_bank_statement_alternate_evidence_routes_to_same_action(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Real manifest fact: BANK_STATEMENT_SUMMARY and CANCELLED_CHEQUE
    both route to the SAME action_id (upload_cancelled_cheque), unlike
    Credit Card's alternate-evidence pattern which used two different
    action_ids for its two income doc types."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "INVESTMENT",
        "goal": {"investment_mode": "ONE_TIME_LUMPSUM", "target_amount": 10000},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(
        _draw_bank_statement, "BANK_STATEMENT_SUMMARY", "statement_standard", seed=10002
    )

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "BANK_STATEMENT_SUMMARY", "expected_snapshot_id": snapshot_id},
        files={"file": ("statement.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()
    assert body["proposed_action_id"] == "upload_cancelled_cheque"
    assert body["consequence_preview"] is not None


async def test_kra_kyc_letter_ai_fact_correct_but_consequence_preview_stays_null(
    client: AsyncClient, session_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
):
    """Documents the disclosed, NOT-fixed manifest routing gap: the AI
    layer correctly determines kra_kyc_validated=True (visible in
    `interpretation.detected`), but no action's `accepts` can correctly
    route a KRA_KYC_LETTER upload (its evidence_mappings action_id points
    to `upload_cancelled_cheque`, whose `satisfies` is
    bank_account_verified, not kra_kyc_validated) - fixing this would
    mean inventing a new action or guessing which one was intended, both
    out of scope this phase."""
    monkeypatch.setattr(settings, "AI_PROVIDER", "local_ml")

    payload = {
        "journey_type": "INVESTMENT",
        "goal": {"investment_mode": "MONTHLY_SIP", "target_amount": 5000},
    }
    create_resp = await client.post("/api/v1/journeys", json=payload, headers=session_headers)
    journey_id = create_resp.json()["journey_id"]
    snapshot_id = create_resp.json()["snapshot_id"]

    image_bytes = _generate_jpeg(_draw_kra_letter, "KRA_KYC_LETTER", "kra_standard", seed=10003)

    ev_resp = await client.post(
        f"/api/v1/journeys/{journey_id}/evidence",
        data={"doc_type": "KRA_KYC_LETTER", "expected_snapshot_id": snapshot_id},
        files={"file": ("kra.jpg", image_bytes, "image/jpeg")},
        headers=session_headers,
    )
    assert ev_resp.status_code == 200
    body = ev_resp.json()

    detected_keys = {d["key"] for d in body["interpretation"]["detected"]}
    assert "kra_kyc_validated" in detected_keys
    assert body["proposed_action_id"] is None
    assert body["consequence_preview"] is None
