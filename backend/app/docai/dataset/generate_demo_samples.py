"""Generates the two judge-facing SYNTHETIC DEMO DOCUMENTS for the
LENDING flagship demo journey (app/packs/manifests/lending.yaml).

Why these two, and only these two: LENDING's `state_schema` has exactly
two mandatory fields that are BLOCKED by default and satisfiable by an
EVIDENCE upload - `monthly_income` (via SALARY_SLIP or BANK_STATEMENT,
see `evidence_mappings`) and `employer_name` (via OFFICE_ID_CARD or
OFFER_LETTER). Every other mandatory field is either pre-satisfied
(kyc_verified, pan_validated, bank_account_linked) or filled by a plain
FORM action a judge can type into directly (employment_type,
loan_offer_accepted) - no document needed. So a judge who uploads these
two documents can walk the ENTIRE real evidence path of the flagship
demo journey without needing a real financial document.

This module deliberately reuses the SAME reportlab drawing functions
(`_draw_salary_slip`, `_draw_offer_letter`) and field values already used
by app/docai/dataset/generate.py's training-data generator and by
app/eval/scenarios/lending/golden.yaml (monthly_income=85000,
employer_name="Acme Technologies India Pvt Ltd") - not new, unverified
document layouts - so what actually gets classified/extracted here is
proven by the very same pipeline that produced the trained
lending_classifier.joblib and by the golden scenario's own numbers.

Output is a real, clean (non-degraded) native-text PDF - the simplest
document class PyMuPDF's text-layer path (app/docai/ocr.py) already
handles with the highest reliability, appropriate for a document meant
to work on the first try for a judge who has never used this app
before.

Every generated document carries a clearly visible
"SYNTHETIC DEMO DOCUMENT - NOT A REAL FINANCIAL RECORD" banner in the
top and bottom margins, placed outside the label-anchored regions the
real extractor scans, so it cannot be mistaken for a real document but
also cannot interfere with real classification/extraction.

Run: `uv run python -m app.docai.dataset.generate_demo_samples`
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.docai.dataset.generate import (
    _draw_offer_letter,
    _draw_salary_slip,
    _fmt_indian_amount,
)

# Matches app/packs/manifests/lending.yaml's own `simulation_defaults`
# and app/eval/scenarios/lending/golden.yaml's golden-path input values -
# not invented numbers.
DEMO_NET_AMT = 85000
DEMO_EMPLOYER_NAME = "Acme Technologies India Pvt Ltd"

WATERMARK_TEXT = (
    "SYNTHETIC DEMO DOCUMENT — NOT A REAL FINANCIAL RECORD — PaytmFlow demo/testing only"
)

OUTPUT_DIR = Path(__file__).resolve().parents[4] / "frontend" / "public" / "demo-documents"


def _demo_fields() -> dict:
    net = DEMO_NET_AMT
    basic = int(net * 0.6)
    hra = int(net * 0.3)
    gross = basic + hra + int(net * 0.15)
    deductions = gross - net
    return {
        "name": "Demo Applicant",
        "employer_name": DEMO_EMPLOYER_NAME,
        "employer_address": "42 MG Road, Bengaluru, Karnataka 560001",
        "designation": "Software Engineer",
        "emp_id": "EMP00000",
        "pay_period": "Jan 2026",
        "net_amt": net,
        "basic_amt": basic,
        "hra_amt": hra,
        "gross_amt": gross,
        "deductions_amt": deductions,
        "misc_amt": 1500,
        "bank_name": "HDFC Bank",
        "account_no": "00000000000",
        "ifsc": "HDFC0000000",
        "_fmt": lambda amt: _fmt_indian_amount(int(amt), "symbol"),
    }


def _add_watermark(c: canvas.Canvas) -> None:
    w, h = A4
    c.saveState()
    c.setFillColorRGB(0.55, 0.55, 0.55)
    c.setFont("Helvetica", 7)
    c.drawCentredString(w / 2, h - 8 * mm, WATERMARK_TEXT)
    c.drawCentredString(w / 2, 8 * mm, WATERMARK_TEXT)
    c.restoreState()


def _render_pdf(draw_fn, fields: dict, template: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c, fields, template)
    _add_watermark(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def generate_demo_samples() -> dict[str, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fields = _demo_fields()

    written: dict[str, Path] = {}

    salary_slip_bytes = _render_pdf(_draw_salary_slip, fields, "salary_table")
    salary_path = OUTPUT_DIR / "sample-salary-slip.pdf"
    salary_path.write_bytes(salary_slip_bytes)
    written["SALARY_SLIP"] = salary_path

    offer_letter_bytes = _render_pdf(_draw_offer_letter, fields, "offer_formal")
    offer_path = OUTPUT_DIR / "sample-offer-letter.pdf"
    offer_path.write_bytes(offer_letter_bytes)
    written["OFFER_LETTER"] = offer_path

    return written


if __name__ == "__main__":
    paths = generate_demo_samples()
    for doc_type, path in paths.items():
        print(f"{doc_type}: {path}")
