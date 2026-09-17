import re
from typing import Any

import pymupdf
import structlog

logger = structlog.get_logger(__name__)

# Canonical Indian Financial Regular Expressions
PAN_PATTERN = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b")
AADHAAR_PATTERN = re.compile(r"\b(\d{4}\s*\d{4}\s*\d{4})\b")
AADHAAR_MASKED_PATTERN = re.compile(r"\b(?:XXXX|xxxx)[- ]?(?:XXXX|xxxx)[- ]?(\d{4})\b")
IFSC_PATTERN = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b",
        re.IGNORECASE,
    ),
]
INCOME_KEYWORD_PATTERN = re.compile(
    r"(?:net\s*pay|gross\s*pay|salary|inflow|monthly\s*income|total\s*credits?|credited\s*amount)\s*[:=-]?\s*(?:₹|Rs\.?|INR|[^\w\s])?\s*([\d,]+(?:\.\d{2})?)",
    re.IGNORECASE,
)
CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?:₹|Rs\.?|INR|[^\w\s])\s*([\d,]+(?:\.\d{2})?)", re.IGNORECASE
)


def extract_text_from_document(content: bytes, mime_type: str) -> str:
    """Extracts text content from a PDF or image document using PyMuPDF."""
    if not content:
        return ""

    if mime_type == "application/pdf":
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
            pages_text = []
            for page in doc:  # type: ignore
                text = page.get_text()
                if text and text.strip():
                    pages_text.append(text.strip())
            return "\n\n".join(pages_text)
        except Exception as exc:
            logger.warning("pymupdf_pdf_extraction_failed", error=str(exc))
            return ""

    # Image files (JPEG/PNG): Return plain text or basic metadata
    if mime_type in ["image/jpeg", "image/png"]:
        return "Image document binary record uploaded."

    return ""


def parse_financial_patterns(text: str) -> dict[str, Any]:
    """Parses PAN, Aadhaar, IFSC, salary/inflow amounts, and dates from raw document text."""
    result: dict[str, Any] = {
        "pan": None,
        "aadhaar": None,
        "ifsc": None,
        "monthly_income": None,
        "detected_amounts": [],
        "detected_dates": [],
    }

    if not text:
        return result

    # 1. PAN detection
    pan_match = PAN_PATTERN.search(text)
    if pan_match:
        result["pan"] = pan_match.group(1).upper()

    # 2. Aadhaar detection
    aadhaar_match = AADHAAR_PATTERN.search(text)
    if aadhaar_match:
        result["aadhaar"] = aadhaar_match.group(1).replace(" ", "")
    else:
        masked_match = AADHAAR_MASKED_PATTERN.search(text)
        if masked_match:
            result["aadhaar"] = f"XXXXXXXX{masked_match.group(1)}"

    # 3. IFSC detection
    ifsc_match = IFSC_PATTERN.search(text)
    if ifsc_match:
        result["ifsc"] = ifsc_match.group(1).upper()

    # 4. Salary / Monthly Income detection
    income_match = INCOME_KEYWORD_PATTERN.search(text)
    if income_match:
        raw_val = income_match.group(1).replace(",", "")
        try:
            result["monthly_income"] = int(float(raw_val))
        except ValueError:
            pass

    # 5. Currency amounts detection
    for match in CURRENCY_AMOUNT_PATTERN.finditer(text):
        raw_val = match.group(1).replace(",", "")
        try:
            amt = int(float(raw_val))
            if amt not in result["detected_amounts"]:
                result["detected_amounts"].append(amt)
        except ValueError:
            pass

    # 6. Dates detection
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            d_str = match.group(1)
            if d_str not in result["detected_dates"]:
                result["detected_dates"].append(d_str)

    return result
