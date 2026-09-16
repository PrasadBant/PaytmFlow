"""Exercises the REAL trained classifier artifact (committed at
app/docai/models/lending_classifier.joblib, trained by
`app/docai/train_classifier.py` against the dataset generator's fixed
SEED - fully reproducible, see app/docai/dataset/generate.py).

These are not mocked - if the classifier is missing (a fresh checkout
that hasn't run the training pipeline), tests skip rather than fake a
result, per the mission's "never fake a result" rule.
"""

import pytest

from app.docai.classifier import get_classifier
from app.docai.ocr import TESSERACT_AVAILABLE

classifier = get_classifier("LENDING")

pytestmark = pytest.mark.skipif(
    classifier is None,
    reason="No trained LENDING classifier artifact present - run app.docai.train_classifier first.",
)


def test_classifies_clean_salary_slip_text_correctly():
    text = (
        "Acme Technologies Pvt Ltd\nPayslip for the month of Jan 2025\n"
        "Employee Name: Test User\nNet Pay ₹85,000"
    )
    result = classifier.classify(
        text, expected_doc_type="SALARY_SLIP", ocr_confidence=0.95, word_count=15
    )
    assert result.outcome == "CORRECT_DOCUMENT"
    assert result.predicted_doc_type == "SALARY_SLIP"


def test_wrong_document_detected():
    text = (
        "OFFER OF EMPLOYMENT\nDear Test User,\nWe are pleased to offer you the "
        "position of Analyst at Acme Technologies Pvt Ltd."
    )
    result = classifier.classify(
        text, expected_doc_type="SALARY_SLIP", ocr_confidence=0.95, word_count=15
    )
    assert result.outcome == "WRONG_DOCUMENT"
    assert result.predicted_doc_type != "SALARY_SLIP"


def test_low_ocr_confidence_reports_unreadable_not_a_guess():
    result = classifier.classify(
        "Net Pay 85000", expected_doc_type="SALARY_SLIP", ocr_confidence=0.1, word_count=3
    )
    assert result.outcome == "UNREADABLE_DOCUMENT"


def test_empty_text_reports_unreadable():
    result = classifier.classify(
        "", expected_doc_type="SALARY_SLIP", ocr_confidence=0.0, word_count=0
    )
    assert result.outcome == "UNREADABLE_DOCUMENT"


def test_alternate_accepted_doc_type_is_correctly_accepted_not_rejected():
    """Human-first real-browser QA regression (BUG-005): an action can
    accept MULTIPLE doc_types (real manifest fact: Lending's
    UPLOAD_INCOME_PROOF accepts either SALARY_SLIP or BANK_STATEMENT). The
    client only ever declares ONE (`expected_doc_type`) when uploading,
    since it has no way to know in advance which of the accepted types
    the user's real file is. Before this fix, a genuine BANK_STATEMENT
    declared as `expected_doc_type="SALARY_SLIP"` was always WRONG_
    DOCUMENT purely because of the single-string comparison - even though
    both are equally valid, manifest-declared evidence for the same
    action. Real bank-statement OCR text, not a synthetic string."""
    text = (
        "HDFC Bank - Account Statement\nAccount Holder: Jeanette Phillips\n"
        "Account No: 89831315230 IFSC: SBINO236806\nDate Description Credit\n"
        "Jun 2002 OPENING BALANCE\nJun 2002 SALARY CREDIT GONZALEZ TRAVIS AND\n"
        "Jun 2002 UTILITY BILL PAYMENT\nRs. 2,05,000\nRs. 1,900"
    )
    result = classifier.classify(
        text,
        expected_doc_type="SALARY_SLIP",
        ocr_confidence=0.95,
        word_count=25,
        accepted_doc_types={"SALARY_SLIP", "BANK_STATEMENT"},
    )
    assert result.outcome == "CORRECT_DOCUMENT"
    assert result.predicted_doc_type == "BANK_STATEMENT"


def test_accepted_doc_types_defaults_to_expected_alone_when_omitted():
    """Backward-compatibility regression: every pre-existing caller that
    never passes `accepted_doc_types` keeps the exact previous single-type
    strict behavior."""
    text = (
        "HDFC Bank - Account Statement\nAccount Holder: Jeanette Phillips\n"
        "Account No: 89831315230 IFSC: SBINO236806\nDate Description Credit\n"
        "Jun 2002 OPENING BALANCE\nJun 2002 SALARY CREDIT GONZALEZ TRAVIS AND\n"
        "Jun 2002 UTILITY BILL PAYMENT\nRs. 2,05,000\nRs. 1,900"
    )
    result = classifier.classify(
        text, expected_doc_type="SALARY_SLIP", ocr_confidence=0.95, word_count=25
    )
    assert result.outcome == "WRONG_DOCUMENT"


def test_unrelated_document_classified_as_other_and_wrong():
    text = "FreshMart Retail - Tax Invoice\nInvoice No: INV-1234\nGroceries 1,240\nTotal 2,100"
    result = classifier.classify(
        text, expected_doc_type="SALARY_SLIP", ocr_confidence=0.95, word_count=10
    )
    assert result.outcome == "WRONG_DOCUMENT"


@pytest.mark.skipif(
    not TESSERACT_AVAILABLE, reason="Tesseract OCR binary not available in this environment."
)
def test_real_generated_document_through_real_ocr_classifies_correctly():
    """End-to-end: renders a genuine synthetic salary slip PDF, rasterizes
    and degrades it exactly like the training dataset does, runs REAL
    Tesseract OCR on the resulting image, and classifies the OCR'd text -
    no step here is mocked."""
    import io
    import random

    import pymupdf
    from PIL import Image
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    from app.docai.dataset.generate import _degrade, _draw_salary_slip, _make_fields

    rng = random.Random(1)
    from faker import Faker

    fake = Faker()
    Faker.seed(1)
    fields = _make_fields(rng, fake, "SALARY_SLIP", "symbol")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_salary_slip(c, fields, "salary_table")
    c.showPage()
    c.save()

    doc = pymupdf.open(stream=buf.getvalue(), filetype="pdf")
    pix = doc[0].get_pixmap(dpi=150)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
    degraded, _ = _degrade(pil_img, rng)
    img_buf = io.BytesIO()
    degraded.save(img_buf, format="JPEG", quality=85)

    from app.docai.ocr import extract_text

    ocr_result = extract_text(img_buf.getvalue(), "image/jpeg")
    assert ocr_result.engine == "tesseract"
    assert ocr_result.word_count > 0

    classification = classifier.classify(
        ocr_result.text,
        expected_doc_type="SALARY_SLIP",
        ocr_confidence=ocr_result.mean_word_confidence,
        word_count=ocr_result.word_count,
    )
    assert classification.outcome == "CORRECT_DOCUMENT"
