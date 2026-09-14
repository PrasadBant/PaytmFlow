"""Integration tests for LocalMLProvider against KYC - the third journey
exercised through the shared local Document AI pipeline, and the first
whose evidence documents carry real, format-validated government
identifiers (passport/EPIC/DL numbers), not just money/text/boolean
facts. Proves the shared architecture (including the BOOLEAN-target-field
fix found while building Insurance) generalizes to KYC with ZERO new
provider code - only new dataset/extraction-vocabulary work was needed.
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
from app.docai.dataset.generate_kyc import (
    _degrade,
    _draw_driving_licence,
    _draw_passport,
    _draw_voter_id,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(get_classifier("KYC") is None, reason="No trained KYC classifier present."),
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


async def test_passport_satisfies_boolean_ovd_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_passport, "PASSPORT_SCAN", "passport_biopage", seed=1001
    )
    manifest = pack_registry.get_pack("KYC")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="PASSPORT_SCAN",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("ovd_document_uploaded") is True


async def test_driving_licence_satisfies_same_boolean_field_as_passport():
    """The manifest's real evidence_mappings quirk: DRIVING_LICENCE maps to
    the SAME action_id as PASSPORT_SCAN (upload_passport_ovd), not a
    separate action - both must satisfy the identical boolean field."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_driving_licence, "DRIVING_LICENCE", "dl_standard", seed=1002
    )
    manifest = pack_registry.get_pack("KYC")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="DRIVING_LICENCE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("ovd_document_uploaded") is True


async def test_no_lending_or_insurance_fields_ever_appear_for_kyc():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_voter_id, "VOTER_ID_CARD", "voter_standard", seed=1003
    )
    manifest = pack_registry.get_pack("KYC")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="VOTER_ID_CARD",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    for forbidden in ("monthly_income", "employer_name", "ped_declaration_submitted"):
        assert forbidden not in result.raw_values
    for d in result.detected:
        assert "Acme Technologies" not in (d.display_value or "")
        assert "85,000" not in (d.display_value or "")


async def test_wrong_document_for_kyc_is_rejected():
    from app.docai.dataset.generate_kyc import _draw_other

    text, ocr_meta, _fields = _render_and_ocr(_draw_other, "OTHER", "receipt", seed=1004)
    manifest = pack_registry.get_pack("KYC")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="PASSPORT_SCAN",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert result.raw_values == {}
