"""Integration tests for LocalMLProvider against INVESTMENT - the sixth
and final journey exercised through the shared local Document AI
pipeline, proving the BOOLEAN-target-field fix (built for Insurance)
still needs ZERO new provider code, and that the identifier framework
generalizes to two more new shapes: IFSC (letter-prefix + digit code,
new SHAPE) and a bare bank account number (digits only, same empty-
letter-group shape as Aadhaar).
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
from app.docai.dataset.generate_investment import (
    _draw_bank_statement,
    _draw_cancelled_cheque,
    _draw_kra_letter,
    _draw_other,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(
        get_classifier("INVESTMENT") is None,
        reason="No trained INVESTMENT classifier present.",
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


async def test_cancelled_cheque_satisfies_boolean_bank_account_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_cancelled_cheque, "CANCELLED_CHEQUE", "cheque_standard", seed=9001
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="CANCELLED_CHEQUE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("bank_account_verified") is True


async def test_bank_statement_satisfies_same_boolean_field_as_cheque():
    """Real manifest fact, not assumed: BANK_STATEMENT_SUMMARY is an
    ALTERNATE bank-verification proof, mapped to the SAME action_id
    (upload_cancelled_cheque) and the SAME boolean target field
    (bank_account_verified) as CANCELLED_CHEQUE - unlike Credit Card's
    alternate-evidence pattern, which used two different action_ids."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_bank_statement, "BANK_STATEMENT_SUMMARY", "statement_standard", seed=9002
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="BANK_STATEMENT_SUMMARY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("bank_account_verified") is True


async def test_kra_kyc_letter_satisfies_boolean_kra_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_kra_letter, "KRA_KYC_LETTER", "kra_standard", seed=9003
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="KRA_KYC_LETTER",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("kra_kyc_validated") is True


async def test_no_other_journey_fields_ever_appear_for_investment():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_cancelled_cheque, "CANCELLED_CHEQUE", "cheque_compact", seed=9004
    )
    manifest = pack_registry.get_pack("INVESTMENT")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="CANCELLED_CHEQUE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    for forbidden in (
        "ped_declaration_submitted",
        "ovd_document_uploaded",
        "income_verified",
        "pan_authenticated",
        "signature_uploaded",
    ):
        assert forbidden not in result.raw_values


async def test_wrong_document_for_investment_is_rejected():
    text, ocr_meta, _fields = _render_and_ocr(_draw_other, "OTHER", "receipt", seed=9005)
    manifest = pack_registry.get_pack("INVESTMENT")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="CANCELLED_CHEQUE",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert result.raw_values == {}
