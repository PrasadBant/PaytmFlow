"""Deterministic normalization for Indian financial document values.

This is intentionally NOT part of the ML model - normalization of a
recognized numeric/date string into a canonical value is a well-defined,
rule-governed transformation (mission Phase 11/12: "AI extracts.
Deterministic validation verifies."), so it lives here as plain,
testable, model-free code that the extraction layer calls after it has
located a candidate string.
"""

from __future__ import annotations

import re
from datetime import datetime

_CURRENCY_PREFIX = re.compile(r"^(?:₹|Rs\.?|INR|[I|l](?=\d))\s*", re.IGNORECASE)
_OCR_DIGIT_CONFUSIONS = {
    "O": "0",
    "o": "0",
    "I": "1",
    "l": "1",
    "S": "5",
    "B": "8",
}


def normalize_indian_amount(raw: str) -> int | None:
    """Parses an Indian-formatted currency string ("₹1,98,000", "Rs. 85,000",
    "INR 85000", "I85,000", "85,000.00") into a plain integer rupee amount.

    Returns None (never a fabricated number) if the string cannot be
    confidently parsed as a number.
    """
    if not raw:
        return None
    text = _CURRENCY_PREFIX.sub("", raw.strip())
    text = text.replace(",", "").strip()
    # Drop a trailing ".00"/".50" style paise fragment - loan/income
    # decisioning in this system operates on whole rupees.
    text = re.sub(r"\.\d{1,2}$", "", text)
    if not re.fullmatch(r"\d+", text):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def try_fix_ocr_digit_confusion(raw: str) -> str:
    """Applies a conservative, contextual fix for the classic OCR digit/letter
    confusions (O/0, I/1, S/5) ONLY inside a token that is otherwise
    entirely digits/punctuation/confusable-letters - i.e. only when the
    surrounding characters already look numeric, so a real word is never
    mangled.

    Guards leading currency symbol glyphs (e.g. 'I' or '|' in 'I85,000' representing
    Rupee / INR font glyph) so they are preserved as currency prefix rather than
    falsely converted to a leading digit '1'.
    """
    raw_str = raw.strip()
    prefix_match = _CURRENCY_PREFIX.match(raw_str)
    prefix = prefix_match.group(0) if prefix_match else ""
    numeric_part = raw_str[len(prefix):]

    def _fix_token(match: re.Match) -> str:
        token = match.group(0)
        return "".join(_OCR_DIGIT_CONFUSIONS.get(c, c) for c in token)

    fixed = re.sub(r"(?<![A-Za-z])[0-9OoIlSB,.]{3,}(?![A-Za-z])", _fix_token, numeric_part)
    return prefix + fixed


_DATE_PATTERNS = [
    ("%d/%m/%Y", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
    ("%d-%m-%Y", re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b")),
    ("%d/%m/%y", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2}\b")),
    ("%b %Y", re.compile(r"\b[A-Za-z]{3,9}\s+\d{4}\b")),
    ("%d %b %Y", re.compile(r"\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\b")),
]


def normalize_date(raw: str) -> str | None:
    """Best-effort normalization of a detected date-like string to ISO
    8601 (YYYY-MM-DD, or YYYY-MM when only month/year is present).
    Returns None rather than guessing if no known pattern matches."""
    raw = raw.strip()
    # Tolerate three recurring, non-fabricating OCR artifacts before
    # parsing - none changes any digit's VALUE, each only undoes a known
    # OCR mangling of a SEPARATOR or a false split within one token:
    # - "/" sometimes misread as "(" (traced: "21/03/1977" -> "21 (03/1977")
    # - a stray comma after a month name (traced: "Aug 2002" -> "Aug, 2002")
    # - a digit run (day, month, or year) split by a falsely inserted
    #   space (traced both mid-day/month: "23/11/2000" -> "23/1 1/2000",
    #   and mid-year: "23/01/1977" -> "23/01/1 977"; same class of
    #   artifact already handled for identifiers in extraction.py).
    #
    # `raw` at this point is always the narrow, already-label-anchored
    # single-date candidate `extract_document_date` matched (see
    # `_DATE_VALUE` in extraction.py), not arbitrary document text, and
    # its non-greedy match already stops at the first complete date - so
    # an unconditional digit-space collapse here can't merge two
    # genuinely different dates together the way doing this over raw
    # document text could.
    cleaned = raw.replace("(", "/").replace(")", "").replace(",", "")
    cleaned = re.sub(r"\s*/\s*", "/", cleaned)
    cleaned = re.sub(r"(?<=\d) (?=\d)", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for fmt, _pattern in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            if fmt == "%b %Y":
                return dt.strftime("%Y-%m")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def normalize_name(raw: str) -> str:
    """Tolerant name normalization: collapses whitespace, title-cases,
    preserves initials (e.g. "R. K. Sharma") - used only for
    cross-document consistency comparison, never for display substitution
    of a value the user didn't provide."""
    collapsed = re.sub(r"\s+", " ", raw.strip())
    return collapsed.title()


def names_match(name_a: str, name_b: str) -> bool:
    """Tolerant equality for cross-document consistency (mission Phase 13):
    case/spacing-insensitive, and tolerant of one name being a subset of
    tokens of the other (e.g. "Marc Estrada" vs "Marc E. Estrada")."""
    a_tokens = set(normalize_name(name_a).split())
    b_tokens = set(normalize_name(name_b).split())
    if not a_tokens or not b_tokens:
        return False
    a_initials = {t[0] for t in a_tokens if t}
    b_initials = {t[0] for t in b_tokens if t}
    overlap = a_tokens & b_tokens
    # Require most tokens to match, allowing initials to stand in for a
    # full token on either side.
    min_len = min(len(a_tokens), len(b_tokens))
    return len(overlap) >= max(1, min_len - 1) or a_initials == b_initials
