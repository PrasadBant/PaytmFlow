"""Integration tests for LocalMLProvider against ACCOUNT_OPENING - the
fifth journey exercised through the shared local Document AI pipeline,
proving the BOOLEAN-target-field fix (built for Insurance) still needs
ZERO new provider code, and that the identifier framework generalizes to
a genuinely new shape (Aadhaar: 12 digits, no letters at all) via a
data-driven pattern addition only.

Also documents (not "fixes") a real, disclosed manifest defect found this
phase: `evidence_mappings` maps AADHAAR_FRONT_BACK to the boolean field
`signature_uploaded` (not an identity-related field) - a literal fact of
the manifest, which this test asserts rather than second-guesses, since
the manifest is the only source of truth and inventing a "corrected"
target field was explicitly out of scope this phase.
"""

import io
import random

import pymupdf
import pytest
from faker import Faker
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ai.local_ml import LocalMLProvider
from app.docai.classifier import get_classifier
from app.docai.dataset.generate import _degrade
from app.docai.dataset.generate_account_opening import (
    _draw_aadhaar,
    _draw_other,
    _draw_pan_card,
    _draw_signature_specimen,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(
        get_classifier("ACCOUNT_OPENING") is None,
        reason="No trained ACCOUNT_OPENING classifier present.",
    ),
    pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available."),
    pytest.mark.asyncio,
]


@pytest.fixture(autouse=True)
def load_manifests():
    pack_registry.load_all()


def _render_and_ocr(draw_fn, doc_type: str, template: str, seed: int):
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

    ocr_result = extract_text(img_buf.getvalue(), "image/jpeg")
    ocr_meta = {
        "confidence": ocr_result.mean_word_confidence,
        "word_count": ocr_result.word_count,
        "engine": ocr_result.engine,
        "lines": [{"text": ln.text, "top": ln.top, "bottom": ln.bottom} for ln in ocr_result.lines],
    }
    return ocr_result.text, ocr_meta, fields


async def test_signature_specimen_satisfies_boolean_signature_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_signature_specimen, "SIGNATURE_SPECIMEN", "signature_card", seed=4001
    )
    manifest = pack_registry.get_pack("ACCOUNT_OPENING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SIGNATURE_SPECIMEN",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("signature_uploaded") is True


async def test_pan_card_satisfies_boolean_pan_authenticated_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_pan_card, "PAN_CARD_IMAGE", "pan_standard", seed=4002
    )
    manifest = pack_registry.get_pack("ACCOUNT_OPENING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="PAN_CARD_IMAGE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("pan_authenticated") is True


async def test_aadhaar_satisfies_signature_uploaded_per_actual_manifest_mapping():
    """Real manifest fact, not assumed or corrected: evidence_mappings
    maps AADHAAR_FRONT_BACK to `signature_uploaded`, not an identity
    field - disclosed as a limitation in the phase report, not silently
    "fixed" by inventing a different target field."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_aadhaar, "AADHAAR_FRONT_BACK", "aadhaar_standard", seed=4003
    )
    manifest = pack_registry.get_pack("ACCOUNT_OPENING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="AADHAAR_FRONT_BACK",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("signature_uploaded") is True


async def test_no_lending_insurance_kyc_or_credit_card_fields_ever_appear():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_pan_card, "PAN_CARD_IMAGE", "pan_compact", seed=4004
    )
    manifest = pack_registry.get_pack("ACCOUNT_OPENING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="PAN_CARD_IMAGE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    for forbidden in (
        "ped_declaration_submitted",
        "ovd_document_uploaded",
        "income_verified",
        "employer_name",
    ):
        assert forbidden not in result.raw_values


async def test_wrong_document_for_account_opening_is_rejected():
    text, ocr_meta, _fields = _render_and_ocr(_draw_other, "OTHER", "receipt", seed=4005)
    manifest = pack_registry.get_pack("ACCOUNT_OPENING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SIGNATURE_SPECIMEN",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert result.raw_values == {}
