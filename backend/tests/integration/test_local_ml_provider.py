"""Integration tests for LocalMLProvider - the real local-inference
AIProvider - against real synthetic documents pushed through real OCR.
Nothing here is mocked: a real PDF is rendered, rasterized and degraded
exactly as the training pipeline does, OCR'd with real Tesseract, and
classified/extracted with the real trained model.
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
from app.docai.dataset.generate import _degrade, _draw_offer_letter, _draw_salary_slip, _make_fields
from app.docai.ocr import TESSERACT_AVAILABLE, extract_text
from app.packs.registry import pack_registry

pytestmark = [
    pytest.mark.skipif(
        get_classifier("LENDING") is None, reason="No trained LENDING classifier present."
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
    fields = _make_fields(rng, fake, doc_type, "symbol")

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


async def test_correct_document_extracts_real_field_not_a_hardcoded_value():
    text, ocr_meta, fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_table", seed=101
    )
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    income_field = next(d for d in result.detected if d.key == "monthly_income")
    # The extracted value must be the ACTUAL randomized amount rendered
    # onto this specific document, not a fixed demo constant - this is
    # the exact defect class (MockAI's hardcoded 85000/Acme) the mission
    # is about eliminating.
    assert income_field.value == fields["net_amt"]
    assert (
        income_field.value != 85000 or fields["net_amt"] == 85000
    )  # no accidental coincidence assumption


async def test_wrong_document_is_detected_not_silently_accepted():
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_offer_letter, "OFFER_LETTER", "offer_formal", seed=202
    )
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    # Uploaded an offer letter but the action expects a SALARY_SLIP.
    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is False
    assert (
        result.detected == []
    )  # never invents fields for a document it doesn't recognize as expected


async def test_income_conflict_against_existing_fields_is_flagged():
    # Reuses seed=101 (verified in the "correct document" test above to
    # extract successfully) rather than a fresh seed, since this test's
    # purpose is the conflict-detection branch specifically, not another
    # independent sample of raw extraction success rate (already measured
    # in app/docai/evaluate_extraction.py's dataset-wide metrics).
    text, ocr_meta, fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_table", seed=101
    )
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    # Simulate a wildly different income already recorded on the journey.
    conflicting_existing = {"monthly_income": fields["net_amt"] + 500_000}

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields=conflicting_existing,
        ocr_meta=ocr_meta,
    )

    assert len(result.conflicts) == 1
    assert result.conflicts[0].field == "monthly_income"


async def test_verified_document_summary_never_contains_a_raw_percentage():
    """Real-browser QA regression: `interpretation.summary` is rendered
    verbatim as `ai-summary-text` on Screen 7, and frontend/CLAUDE.md rule
    1 is absolute - "NEVER render a percentage". The live app's real
    summary text used to read "...confidence 73%.", confirmed via a real
    user's own screenshot. The measured `confidence` float must still be
    returned on `AIInterpretationResult.confidence` (never removed) - it
    must just never be turned into displayed percentage text."""
    text, ocr_meta, _fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_table", seed=101
    )
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields={},
        ocr_meta=ocr_meta,
    )

    assert result.verified is True
    assert isinstance(result.confidence, float) and result.confidence > 0.0
    assert "%" not in result.summary


async def test_small_income_variance_within_tolerance_is_not_flagged():
    # Integrity-hardening phase fix: this consistency comparison now
    # actually calls `check_income_consistency` (app/docai/consistency.py)
    # instead of a plain `!=` - that tolerance-aware function existed and
    # was unit-tested since Lending's own phase, but was never wired into
    # any real code path until now. A benign small difference (well
    # within the function's own 10% tolerance) between two independently
    # reported income figures - e.g. a salary slip vs a bank statement,
    # differing only by minor deductions - must NOT be flagged as a
    # conflict, unlike the wildly-different case above.
    text, ocr_meta, fields = _render_and_ocr(
        _draw_salary_slip, "SALARY_SLIP", "salary_table", seed=101
    )
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    # 3% higher than the real figure - comfortably inside the 10% band.
    close_existing = {"monthly_income": int(fields["net_amt"] * 1.03)}

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=text,
        manifest=manifest,
        existing_fields=close_existing,
        ocr_meta=ocr_meta,
    )

    assert result.conflicts == []
    assert result.verified is True


async def test_unsupported_journey_returns_safe_not_fabricated_result(
    monkeypatch: pytest.MonkeyPatch,
):
    # All six journeys (LENDING, INSURANCE, KYC, CREDIT_CARD,
    # ACCOUNT_OPENING, INVESTMENT) now have a trained classifier - see
    # app/docai/__init__.py's scope note - so there is no longer any
    # REAL, still-uncovered journey this test can point at (each prior
    # phase retargeted it to whichever journey was still uncovered;
    # Investment was the last one). The test's actual intent - "when
    # `get_classifier()` returns None for a journey, report an honest
    # 'not analyzed' result rather than fabricating output" - is still a
    # real code path worth covering, so it's now exercised directly by
    # monkeypatching `get_classifier` for this one call, using a real
    # manifest (LENDING's) so everything else about the call stays
    # genuine.
    import app.ai.local_ml as local_ml_module

    monkeypatch.setattr(local_ml_module, "get_classifier", lambda _journey_type: None)

    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SOME_DOC_TYPE",
        extracted_text="some document text",
        manifest=manifest,
        existing_fields={},
    )

    # No trained classifier exists for this journey - must report an
    # honest "not analyzed", never a fabricated detected field or a
    # confident-looking guess.
    assert result.verified is False
    assert result.detected == []
    assert result.confidence == 0.0


async def test_salary_slip_internal_calculation_conflict_flagged():
    salary_slip_text = """
    EMPLOYEE PAYSLIP - ACME TECHNOLOGIES PVT LTD
    Employee Name: Rahul Sharma
    Designation: Senior Software Engineer
    Month: March 2026

    Gross Earnings: ₹80,000
    Total Deductions: ₹12,000
    Net Pay: ₹90,000
    """
    manifest = pack_registry.get_pack("LENDING")
    provider = LocalMLProvider()

    result = await provider.reconcile_evidence(
        doc_type="SALARY_SLIP",
        extracted_text=salary_slip_text,
        manifest=manifest,
        existing_fields={},
    )

    assert result.verified is False
    assert len(result.conflicts) == 1
    assert result.conflicts[0].field == "monthly_income"
    assert "Gross Earnings (₹80,000)" in result.conflicts[0].message
    assert "Total Deductions (₹12,000)" in result.conflicts[0].message
    assert "₹68,000" in result.conflicts[0].message
    assert "Net Pay (₹90,000)" in result.conflicts[0].message
    assert "internal value inconsistencies were detected" in result.summary

