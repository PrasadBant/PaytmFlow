"""Real PyMuPDF text-layer extraction tests (app/docai/ocr.py).

Human-real-user QA regression (BUG-008): a genuine, real, born-digital
PDF (`paytmflow_salary_slip_demo_accepted.pdf`, provided by the user
during live testing - not a filename-specific hack; this test reproduces
its LAYOUT PATTERN generically, not the literal file) laid its
"Monthly Net Income" label and "133,000 INR" value out as two side-by-side
table CELLS on the same printed row, in different PyMuPDF text "lines".
`extract_pdf_text_layer()` never populated `OcrResult.lines` at all, so
`_find_amount_near_label`'s existing cross-line, same-visual-row matching
(already built and working for Tesseract-OCR'd images with this exact
layout shape) never had any position data to work with for a native-text
PDF - only its same-printed-line search ran, which can never find a
label and value that are genuinely on separate text lines even though
they are visually the same row.
"""

import io

import pymupdf
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.docai.extraction import extract_monthly_income
from app.docai.ocr import extract_pdf_text_layer


def _two_column_salary_pdf(label: str, value: str) -> bytes:
    """A genuine, real, born-digital PDF (no rasterization, no OCR - a
    real PyMuPDF text layer) with `label` and `value` printed as two
    side-by-side table cells on the SAME row - the real layout pattern
    that exposed this bug, built generically (any label/value pair), not
    tied to one document's exact wording."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(60, h - 60, "MONTHLY SALARY SLIP")
    c.setFont("Helvetica", 10)
    c.drawString(60, h - 100, "Field")
    c.drawString(300, h - 100, "Value")
    c.drawString(60, h - 130, "Document Type")
    c.drawString(300, h - 130, "SALARY_SLIP")
    # The row that actually broke: label and value as two separate table
    # cells, same row, real horizontal gap between them.
    c.drawString(60, h - 160, label)
    c.drawString(300, h - 160, value)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_native_text_pdf_populates_ocr_lines_with_real_positions():
    pdf_bytes = _two_column_salary_pdf("Monthly Net Income", "133,000 INR")
    result = extract_pdf_text_layer(pdf_bytes)

    assert result.engine == "pymupdf_text_layer"
    assert result.lines, "a native-text PDF must produce real per-line position data"

    label_line = next(ln for ln in result.lines if ln.text == "Monthly Net Income")
    value_line = next(ln for ln in result.lines if ln.text == "133,000 INR")
    # Same printed row -> (near-)identical vertical position, genuinely
    # measured from PyMuPDF's own line bounding boxes, not fabricated.
    assert abs(label_line.top - value_line.top) < 5
    assert abs(label_line.bottom - value_line.bottom) < 5


def test_label_and_value_in_separate_table_columns_are_correctly_extracted():
    """The actual end-to-end regression: extraction must succeed for a
    label/value pair that are genuinely on the same visual row but
    different PyMuPDF text lines - not just when they happen to share one
    printed line."""
    pdf_bytes = _two_column_salary_pdf("Monthly Net Income", "133,000 INR")
    result = extract_pdf_text_layer(pdf_bytes)

    field = extract_monthly_income(result.text, "SALARY_SLIP", lines=result.lines)

    assert field.value == 133000
    assert field.validated is True


def test_without_lines_data_same_row_different_column_extraction_fails():
    """Regression-proof: confirms the SAME text, stripped of its real line
    position data (simulating the pre-fix behavior where `lines` was
    always empty for a native-text PDF), genuinely cannot find a same-row/
    different-column value via the same-printed-line search alone - this
    is the exact failure the user reported, reproduced deterministically,
    not merely asserted away."""
    pdf_bytes = _two_column_salary_pdf("Monthly Net Income", "133,000 INR")
    result = extract_pdf_text_layer(pdf_bytes)

    field_without_lines = extract_monthly_income(result.text, "SALARY_SLIP", lines=[])
    assert field_without_lines.value is None
    assert field_without_lines.validation_note is not None


def test_no_text_layer_pdf_still_returns_empty_result_safely():
    """Defensive regression: a PDF with genuinely no extractable text (a
    single blank page) must not error and must report no lines, not a
    fabricated one."""
    buf = io.BytesIO()
    doc = pymupdf.open()
    doc.new_page()
    doc.save(buf)
    result = extract_pdf_text_layer(buf.getvalue())
    assert result.text == ""
    assert result.lines == []
    assert result.degraded_reason == "no_text_layer"
