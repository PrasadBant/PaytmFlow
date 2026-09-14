"""Integration tests for LocalMLProvider against INSURANCE - the first
non-Lending journey exercised through the shared local Document AI
pipeline. Proves two things real synthetic documents alone can't:
(1) the classifier/extractor genuinely work on Insurance's own content
(medical/policy documents, never Lending fields), and (2) the BOOLEAN-
target-field fix in local_ml.py (found while auditing Insurance's
manifest - Lending has no boolean evidence_mappings target) actually
verifies a correctly-classified document instead of always reporting
verified=False.
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
from app.docai.dataset.generate_insurance import (
    _degrade,
    _draw_discharge_summary,
    _draw_policy_copy,
    _make_fields,
)
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(
        get_classifier("INSURANCE") is None, reason="No trained INSURANCE classifier present."
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


async def test_correct_medical_document_satisfies_boolean_target_field():
    """The core fix this phase: Insurance's evidence_mappings target
    (`ped_declaration_submitted`) is BOOLEAN, not money/text. Before the
    fix, LocalMLProvider always returned verified=False for any
    boolean-target journey since no money/text VALUE was ever extracted -
    this proves a correctly classified medical document now genuinely
    satisfies the field."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_discharge_summary, "MEDICAL_DISCHARGE_SUMMARY", "discharge_formal", seed=901
    )
    manifest = pack_registry.get_pack("INSURANCE")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="MEDICAL_DISCHARGE_SUMMARY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("ped_declaration_submitted") is True
    detected_keys = {d.key for d in result.detected}
    assert "ped_declaration_submitted" in detected_keys


async def test_alternate_accepted_doc_type_also_satisfies_same_boolean_field():
    """All 3 of Insurance's accepted doc types map to the SAME boolean
    field - a PREVIOUS_POLICY_COPY must satisfy it exactly like a
    discharge summary does, proving this isn't hardcoded to one doc_type."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_policy_copy, "PREVIOUS_POLICY_COPY", "policy_schedule", seed=902
    )
    manifest = pack_registry.get_pack("INSURANCE")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="PREVIOUS_POLICY_COPY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert result.raw_values.get("ped_declaration_submitted") is True


async def test_no_lending_fields_or_copy_ever_appears_for_insurance():
    """A correct Insurance document must never surface Lending's fields
    (monthly_income, employer_name) or its fixture values."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_discharge_summary, "MEDICAL_DISCHARGE_SUMMARY", "discharge_compact", seed=903
    )
    manifest = pack_registry.get_pack("INSURANCE")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="MEDICAL_DISCHARGE_SUMMARY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert "monthly_income" not in result.raw_values
    assert "employer_name" not in result.raw_values
    for d in result.detected:
        assert d.key not in ("monthly_income", "employer_name")
        assert "Acme Technologies" not in (d.display_value or "")
        assert "85,000" not in (d.display_value or "")


async def test_wrong_document_for_insurance_is_still_rejected():
    """A genuinely unrelated (OTHER/junk) document must still be
    correctly rejected for Insurance, exactly as for Lending - the
    wrong-document safety mechanism is journey-agnostic."""
    from app.docai.dataset.generate_insurance import _draw_other

    text, ocr_meta, _fields = _render_and_ocr(_draw_other, "OTHER", "receipt", seed=904)
    manifest = pack_registry.get_pack("INSURANCE")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="MEDICAL_DISCHARGE_SUMMARY",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert result.raw_values == {}
