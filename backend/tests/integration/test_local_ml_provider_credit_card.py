"""Integration tests for LocalMLProvider against CREDIT_CARD - the fourth
journey exercised through the shared local Document AI pipeline, and the
first whose evidence documents carry a PAN (5-letter-prefix + 4-digit +
1-letter format), proving the identifier framework built for KYC
generalizes to a THIRD identifier shape with only a data-driven pattern
addition, and proving the BOOLEAN-target-field fix (built for Insurance)
still needs ZERO new provider code here either.
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
from app.docai.dataset.generate_credit_card import (
    _draw_itr,
    _draw_other,
    _draw_salary_slip,
    _draw_utility_bill,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(
        get_classifier("CREDIT_CARD") is None, reason="No trained CREDIT_CARD classifier present."
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


async def test_salary_slip_satisfies_boolean_income_field():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_table", seed=2001
    )
    manifest = pack_registry.get_pack("CREDIT_CARD")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("income_verified") is True


async def test_itr_satisfies_same_boolean_field_as_salary_slip():
    """The manifest's real evidence_mappings quirk: ITR_V_ACKNOWLEDGEMENT
    is an ALTERNATE income proof, mapping to a different action_id
    (upload_it_return, not upload_salary_statement) but the SAME boolean
    target field (income_verified) as SALARY_SLIP."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_itr, "ITR_V_ACKNOWLEDGEMENT", "itr_formal", seed=2002
    )
    manifest = pack_registry.get_pack("CREDIT_CARD")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="ITR_V_ACKNOWLEDGEMENT",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("income_verified") is True


async def test_utility_bill_satisfies_current_address_verified():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_utility_bill, "UTILITY_BILL_ELECTRICITY", "utility_standard", seed=2003
    )
    manifest = pack_registry.get_pack("CREDIT_CARD")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="UTILITY_BILL_ELECTRICITY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("current_address_verified") is True


async def test_no_lending_insurance_or_kyc_fields_ever_appear_for_credit_card():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_compact", seed=2004
    )
    manifest = pack_registry.get_pack("CREDIT_CARD")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    for forbidden in ("ped_declaration_submitted", "ovd_document_uploaded", "employer_name"):
        assert forbidden not in result.raw_values


async def test_wrong_document_for_credit_card_is_rejected():
    text, ocr_meta, _fields = _render_and_ocr(_draw_other, "OTHER", "receipt", seed=2005)
    manifest = pack_registry.get_pack("CREDIT_CARD")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert result.raw_values == {}
