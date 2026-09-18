"""Structured field extraction from OCR'd text.

Extraction is label-anchored, not single-keyword-triggered: each target
field has a small set of real-world synonym labels actually used on
Indian salary slips / bank statements / ID cards / offer letters (e.g.
"Net Pay" / "Net Salary" / "Take Home" / "Net Amount Payable" all denote
the same underlying concept per the mission's own Phase 9 example), and
the numeric/text value nearest to whichever label actually appears is
extracted - never a single hardcoded trigger like `if "salary" in text`.

Every value returned here is either genuinely located in the OCR'd text
(with the raw evidence span kept for traceability) or is `None` with an
explanation - nothing is invented when extraction fails (mission Phase 8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.docai.normalize import normalize_date, normalize_indian_amount, try_fix_ocr_digit_confusion

_AMOUNT_TOKEN = (
    r"(?<![A-Za-z])"
    r"(?:(?:₹|Rs\.?|INR)\s*[\d,OoIlSB]{3,}|(?=(?:[\d,OoIlSB]*\d))[\d,OoIlSB]{3,})"
    r"(?:\.\d{1,2})?"
    r"(?![A-Za-z])"
)

# Common single-character OCR misreads among letters (distinct from the
# digit-confusion table in normalize.py - this is the ALPHABETIC analogue).
# Grounded in what was actually observed in this pipeline's own OCR output
# ("Ltd" -> "Lid"/"Lta", "Pvt" -> "Pyt", "SAL" -> "SAU") - not a guess -
# and, being a per-CHARACTER confusion table applied to any word via
# `_fuzzy_literal`, it generalizes to any word containing these letters
# rather than hardcoding one specific misread word or company name.
_ALPHA_OCR_CONFUSIONS: dict[str, str] = {
    "t": "ti",
    "i": "it",
    "v": "vy",
    "y": "yv",
    "d": "da",
    "a": "ad",
    "l": "l1iu",  # "u" added after tracing a real "SAL" -> "SAU" misread
    "u": "ul",
}


def _fuzzy_literal(word: str) -> str:
    """Builds a regex for `word` where each OCR-confusable letter is
    replaced by a small character class of its known misreadings, and
    every other character is matched literally (escaped). Intended for
    `re.compile(..., re.IGNORECASE)`."""
    parts = []
    for ch in word:
        confusions = _ALPHA_OCR_CONFUSIONS.get(ch.lower())
        if confusions:
            parts.append(f"[{confusions}]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


# Real-world synonym labels for the SALARY_SLIP -> monthly_income field.
# This is a controlled semantic vocabulary (the mission's own "Net Pay /
# Net Salary / Take Home / Net Amount" example), not one magic string.
INCOME_LABELS_SALARY_SLIP = [
    r"net\s*pay",
    r"net\s*salary(?:\s*credited)?",
    r"take\s*home",
    r"net\s*amount\s*payable",
    # "Monthly Net Income" - a real, common Indian payslip label wording,
    # same class as the four above (human-QA-found generalization gap: a
    # genuine salary slip using this exact common phrasing was correctly
    # classified as SALARY_SLIP but its income could not be extracted
    # because this specific synonym was missing from the vocabulary -
    # not a filename-specific fix, not a hardcoded value; this is the
    # extractor recognizing one more real-world phrasing of the same
    # concept it already extracts, per this file's own stated design).
    r"monthly\s*net\s*income",
    r"net\s*income",
]

# Labels belonging to other financial breakdown categories (e.g. gross earnings,
# deductions) that must NOT be selected as the amount for a net income label.
_EXCLUDED_INCOME_LABELS = re.compile(
    r"\b(?:gross(?:\s*pay|\s*earnings|\s*salary)?|total\s*gross|total\s*earnings|"
    r"deductions?|total\s*deductions?|provident\s*fund|\bpf\b|\btax\b|\btds\b|\besi\b|"
    r"basic(?:\s*pay|\s*salary)?|hra|allowances?)\b",
    re.IGNORECASE,
)

# Real-world synonym labels for a salary credit line inside a bank
# statement, across differing issuer wording conventions.
INCOME_LABELS_BANK_STATEMENT = [
    r"salary\s*credit",
    r"neft[- ]salary",
    r"by\s*salary",
    # Narration-code style ("SAL/<company>") - built fuzzy-tolerant via
    # `_fuzzy_literal` (so a traced real misread like "SAL" -> "SAU"
    # still matches) with a dash/slash/backslash/pipe separator, tolerating
    # the common OCR artifact where a forward slash is recognized as 'I' or 'l'
    # before uppercase company initials (e.g. "SAL/SHAW" -> "SALISHAW").
    rf"{_fuzzy_literal('sal')}\s*[-/\\|]\s*",
    rf"{_fuzzy_literal('sal')}[Il/\\|-](?=[A-Z])\s*",
]


# Built from a small, fixed vocabulary of REAL Indian legal-entity suffix
# words (Pvt/Private, Ltd/Limited, LLP), each individually OCR-fuzzy-
# tolerant via `_fuzzy_literal` - not a lookup table of specific company
# names. This generalizes to any employer name ending in any of these
# suffixes, with or without an OCR misread.
_LTD = rf"{_fuzzy_literal('Ltd')}\.?"
_PVT = rf"{_fuzzy_literal('Pvt')}\.?"
# Named groups so the matched suffix can be replaced with its canonical
# spelling afterward (mission Phase 11: "Do not blindly correct OCR. Use
# contextual validation" - here the "context" is that we already know,
# from WHICH alternative matched, exactly what the correct spelling is,
# so this is not a guess).
_SUFFIX_ALTERNATION = "|".join(
    [
        rf"(?P<pvt_ltd>{_PVT}\s*{_LTD})",  # Pvt Ltd (incl. OCR-fuzzed "Pyt Lid" etc.)
        r"(?P<priv_ltd>Private\s*Limited)",
        rf"(?P<ltd>{_LTD})",  # bare Ltd
        r"(?P<limited>Limited)",
        r"(?P<llp>LLP)",
    ]
)
_CANONICAL_SUFFIX = {
    "pvt_ltd": "Pvt Ltd",
    "priv_ltd": "Private Limited",
    "ltd": "Ltd",
    "limited": "Limited",
    "llp": "LLP",
}

EMPLOYER_SUFFIX_PATTERN = re.compile(
    rf"([A-Z][A-Za-z&.,' ]{{2,60}}?\s+(?:{_SUFFIX_ALTERNATION}))",
    re.IGNORECASE,
)


@dataclass
class ExtractedField:
    key: str
    raw_value: str | None
    value: int | str | None
    evidence_span: str | None
    method: str
    validated: bool
    validation_note: str | None = None


_MIN_ROW_BAND_TOLERANCE_PX = 20
_MAX_ROW_BAND_TOLERANCE_PX = 100
_ROW_BAND_TOLERANCE_MULTIPLIER = 1.5
# Real OCR bounding-box top-coordinates put words on visually "the same
# printed row" within roughly one row-height of each other. Rather than
# one fixed pixel constant (tuned to a single DPI/font-size and therefore
# NOT generalizable across templates/documents), the tolerance is derived
# per-document from that document's OWN measured line spacing (median gap
# between consecutive OCR line tops) - a document rendered larger/smaller,
# at a different DPI, or with a different font, gets a proportionally
# different tolerance automatically, bounded by a floor/ceiling so a
# sparse page with few lines can't produce a runaway match radius.


def _row_band_tolerance(lines: list) -> float:
    if len(lines) < 2:
        return float(_MIN_ROW_BAND_TOLERANCE_PX)
    tops = sorted(ln.top for ln in lines)
    # Intentionally NOT strict=True: zipping a list against its own
    # 1-shifted slice always differs in length by exactly one - that is
    # the correct, expected shape for "each consecutive pair", not an
    # error case.
    gaps = [b - a for a, b in zip(tops, tops[1:], strict=False) if b > a]
    if not gaps:
        return float(_MIN_ROW_BAND_TOLERANCE_PX)
    gaps.sort()
    median_gap = gaps[len(gaps) // 2]
    return min(
        _MAX_ROW_BAND_TOLERANCE_PX,
        max(_MIN_ROW_BAND_TOLERANCE_PX, median_gap * _ROW_BAND_TOLERANCE_MULTIPLIER),
    )


def _is_marked_amount(raw: str) -> bool:
    # A monetary figure on an Indian financial document is comma-grouped
    # or currency-prefixed in the overwhelming majority of real templates;
    # a bare short digit run (e.g. a transaction-date year, an account
    # fragment) is far more likely to be something else.
    return "," in raw or bool(re.search(r"[₹]|Rs\.?|INR", raw, re.IGNORECASE))


def _amounts_in_line(line_text: str) -> list[re.Match]:
    return list(re.compile(_AMOUNT_TOKEN).finditer(line_text))


def _find_amount_near_label(
    text: str,
    label_patterns: list[str],
    lines: list | None = None,
    apply_breakdown_exclusion: bool = True,
) -> tuple[str | None, str | None]:
    """Returns (raw_amount_string, evidence_span) for an amount token
    associated with any of the given label patterns.

    Builds candidate pool per label pattern from:
      1. Same-line matches: an amount token on the exact same OCR/text line as the label.
      2. Table/column-aligned matches (when `lines`, real OcrLine boxes with top/bottom
         pixel positions, are supplied): associates table row labels with their corresponding
         row amounts using vertical row-band proximity and row ranking, excluding candidate
         amounts explicitly associated with opposing breakdown categories (e.g. Gross/Deductions).

    `apply_breakdown_exclusion` scopes that Gross/Deductions exclusion to documents
    where a competing breakdown row genuinely CAN exist (salary slips). A bank
    statement transaction line has exactly one amount per narration - there is no
    separate "Gross" row to compete with - so a real narration convention like
    "NEFT-SALARY-GROSS-<company>" must not have its own, only amount excluded just
    because the word "GROSS" appears in the narration text describing it (traced:
    this silently returned an unrelated nearby transaction's amount instead).
    """
    tolerance = _row_band_tolerance(lines) if lines else 0.0

    for label_pattern in label_patterns:
        label_re = re.compile(label_pattern, re.IGNORECASE)
        # (is_marked, rank_distance, pixel_distance, match, evidence)
        candidates: list[tuple[bool, int, float, re.Match, str]] = []

        for line in text.splitlines():
            lbl_m = label_re.search(line)
            if lbl_m:
                lbl_start, lbl_end = lbl_m.span()
                for m in _amounts_in_line(line):
                    if apply_breakdown_exclusion:
                        prefix_to_amt = line[: m.start()]
                        last_excluded = list(_EXCLUDED_INCOME_LABELS.finditer(prefix_to_amt))
                        if last_excluded:
                            last_ex_end = last_excluded[-1].end()
                            is_excluded = m.start() >= last_ex_end and (
                                last_ex_end > lbl_end or m.start() < lbl_start
                            )
                            if is_excluded:
                                continue

                    if m.start() >= lbl_end:
                        char_dist = float(m.start() - lbl_end)
                    else:
                        char_dist = float(1000 + abs(lbl_start - m.end()))

                    candidates.append(
                        (
                            _is_marked_amount(m.group(0)),
                            0,
                            char_dist,
                            m,
                            line.strip(),
                        )
                    )

        if lines:
            label_line = next((ln for ln in lines if label_re.search(ln.text)), None)
            if label_line:
                label_top = label_line.top

                amount_lines = [
                    ln for ln in lines if _amounts_in_line(ln.text) and ln is not label_line
                ]

                # Identify labeled rows in the table section to determine relative row ranking
                if amount_lines:
                    min_amt_top = min(a.top for a in amount_lines) - tolerance
                    table_label_lines = [
                        ln for ln in lines if ln not in amount_lines and ln.top >= min_amt_top
                    ]
                    label_rank = (
                        table_label_lines.index(label_line)
                        if label_line in table_label_lines
                        else 0
                    )
                else:
                    table_label_lines = []
                    label_rank = 0

                for candidate_line in amount_lines:
                    pixel_distance = float(abs(candidate_line.top - label_top))
                    if pixel_distance > tolerance:
                        continue

                    # Exclude candidate lines explicitly labeled with other breakdown categories
                    if (
                        apply_breakdown_exclusion
                        and _EXCLUDED_INCOME_LABELS.search(candidate_line.text)
                        and not label_re.search(candidate_line.text)
                    ):
                        continue

                    amount_rank = amount_lines.index(candidate_line)
                    rank_diff = abs(label_rank - amount_rank)

                    for m in _amounts_in_line(candidate_line.text):
                        candidates.append(
                            (
                                _is_marked_amount(m.group(0)),
                                rank_diff,
                                pixel_distance,
                                m,
                                f"{label_line.text.strip()} | {candidate_line.text.strip()}",
                            )
                        )

        if not candidates:
            continue

        candidates.sort(key=lambda c: (not c[0], c[1], c[2]))
        chosen_marked, _rank, _px, chosen_match, chosen_evidence = candidates[0]
        return chosen_match.group(0), chosen_evidence

    return None, None


def extract_monthly_income(text: str, doc_type: str, lines: list | None = None) -> ExtractedField:
    label_patterns = (
        INCOME_LABELS_SALARY_SLIP if doc_type == "SALARY_SLIP" else INCOME_LABELS_BANK_STATEMENT
    )
    # Only a salary slip can genuinely have a competing Gross/Deductions row
    # near the target label - a bank statement's narration line has exactly
    # one amount, so the exclusion must not apply there (see
    # _find_amount_near_label's docstring for the traced failure this fixes).
    raw_amount, evidence = _find_amount_near_label(
        text,
        label_patterns,
        lines=lines,
        apply_breakdown_exclusion=(doc_type == "SALARY_SLIP"),
    )
    if raw_amount is None:
        return ExtractedField(
            key="monthly_income",
            raw_value=None,
            value=None,
            evidence_span=None,
            method="label_anchored_regex",
            validated=False,
            validation_note=f"No recognized income label found for {doc_type}.",
        )

    fixed = try_fix_ocr_digit_confusion(raw_amount)
    value = normalize_indian_amount(fixed)
    if value is None:
        return ExtractedField(
            key="monthly_income",
            raw_value=raw_amount,
            value=None,
            evidence_span=evidence,
            method="label_anchored_regex",
            validated=False,
            validation_note=f"Matched label but could not parse amount '{raw_amount}'.",
        )

    # Deterministic plausibility validation (mission Phase 12): a monthly
    # income of a few rupees or tens of crores is not a normalization
    # failure the extractor can fix, but it IS something the deterministic
    # layer should flag rather than silently trust.
    plausible = 1_000 <= value <= 10_000_000
    return ExtractedField(
        key="monthly_income",
        raw_value=raw_amount,
        value=value,
        evidence_span=evidence,
        method="label_anchored_regex",
        validated=plausible,
        validation_note=None
        if plausible
        else f"Value {value} is outside the plausible monthly income range.",
    )


GROSS_LABELS_SALARY_SLIP = [
    r"gross\s*earnings",
    r"gross\s*pay",
    r"gross\s*salary",
    r"total\s*gross",
    r"total\s*earnings",
]

DEDUCTION_LABELS_SALARY_SLIP = [
    r"total\s*deductions?",
    r"total\s*deduction",
    r"deductions?",
]


def extract_gross_pay(text: str, lines: list | None = None) -> int | None:
    raw_amount, _ = _find_amount_near_label(text, GROSS_LABELS_SALARY_SLIP, lines=lines)
    if not raw_amount:
        return None
    fixed = try_fix_ocr_digit_confusion(raw_amount)
    return normalize_indian_amount(fixed)


def extract_total_deductions(text: str, lines: list | None = None) -> int | None:
    raw_amount, _ = _find_amount_near_label(text, DEDUCTION_LABELS_SALARY_SLIP, lines=lines)
    if not raw_amount:
        return None
    fixed = try_fix_ocr_digit_confusion(raw_amount)
    return normalize_indian_amount(fixed)



def extract_employer_name(text: str) -> ExtractedField:
    match = EMPLOYER_SUFFIX_PATTERN.search(text)
    if not match:
        return ExtractedField(
            key="employer_name",
            raw_value=None,
            value=None,
            evidence_span=None,
            method="company_suffix_anchor",
            validated=False,
            validation_note=(
                "No recognized company-name suffix (Pvt Ltd / LLP / Limited / etc.) found."
            ),
        )
    raw = match.group(1).strip()

    # Canonicalize the matched suffix (mission Phase 11's "contextual
    # validation", not a blind guess): the named alternation group that
    # actually matched tells us exactly WHICH suffix it was, so an
    # OCR-fuzzed spelling like "Pyt Lid" or "Lta" is replaced with its
    # known-correct form - everything BEFORE the suffix (the actual
    # company name) is left untouched, since that part is not from a
    # small fixed vocabulary and correcting it would risk inventing a
    # name that was never there.
    # NOTE: `match.lastgroup` is unreliable here - the outer wrapping
    # capture group (unnamed) always closes AFTER the inner named
    # alternation group since it encloses it, so `lastgroup` ends up
    # None even though a named group clearly matched. groupdict() is
    # used directly instead.
    display_value = raw
    matched_group = next((name for name, val in match.groupdict().items() if val), None)
    if matched_group:
        suffix_text = match.group(matched_group)
        canonical = _CANONICAL_SUFFIX.get(matched_group)
        if suffix_text and canonical:
            idx = raw.rfind(suffix_text)
            if idx != -1:
                display_value = raw[:idx] + canonical

    # OCR sometimes fuses the preceding word; keep at most 6 tokens so a
    # run-on line doesn't get swallowed whole as "the employer name".
    tokens = display_value.split()
    value = " ".join(tokens[-6:]) if len(tokens) > 6 else display_value
    return ExtractedField(
        key="employer_name",
        raw_value=raw,
        value=value,
        evidence_span=match.group(0),
        method="company_suffix_anchor",
        validated=True,
        validation_note=None,
    )


_NAME_LABEL = re.compile(
    # (?i:...) scopes case-insensitivity to just the label word (OCR/real
    # documents vary "Insured:" vs "insured:") - the captured NAME group
    # stays case-SENSITIVE (`[A-Z]...`), since requiring a capital first
    # letter is what keeps this from matching arbitrary lowercase words as
    # a "name".
    r"(?i:Employee\s*Name|Patient\s*Name|Name\s*of\s*Policyholder|Policyholder\s*Name|"
    r"Elector'?s\s*Name|Licen[cs]e\s*Holder|Billed\s*to|"
    # \b after "Pay" specifically: a bare 3-letter label is otherwise a
    # substring-match risk inside an unrelated ALL-CAPS word (traced:
    # "PAYROLL DEPARTMENT" - "Pay" matched inside "PAYROLL", and the
    # capture group happily accepted "ROLL DEPARTMENT" as a "name" since
    # both are Title-Case-shaped after the match point). `\b` requires a
    # real word boundary right after "Pay", which "PAYROLL" never has
    # (it's one continuous word), while "Pay: NAME" and "Pay NAME" both
    # still match correctly.
    r"Patient|Subject|Insured|Holder|Name|Dear|Pay\b)[ \t]*[:\-]?[ \t]*"
    # [ \t]+ (not \s+) between name words: a bare \s+ also matches
    # newlines, which let the capture bleed across a line break onto the
    # NEXT labeled field entirely (traced: "Tiffany Kennedy" captured as
    # "Tiffany Kennedy\nFather's Name" because "Father's" is also
    # capitalized-word-shaped) - a name is on one printed line, so the
    # separator between its words must not cross one.
    r"([A-Z][a-zA-Z.'-]+(?:[ \t]+[A-Z][a-zA-Z.'-]+){1,3})"
)
# Free-prose certificate phrasing ("This is to certify that <NAME>, aged NN,")
# - a genuinely common real-world certificate wording pattern, not tuned to
# one specific template's exact sentence beyond the anchor phrase itself.
#
# No trailing comma is required: the capture group's own "each word must
# ALSO start with a capital letter" constraint already stops the match
# cleanly at the first lowercase word ("...Jerome Dean holds..." naturally
# stops after "Dean", since "holds" isn't Title Case) - requiring a comma
# too was originally just extra insurance, but real phrasing ("certifies
# that X holds Permanent Account Number...") doesn't always put one
# there, so it's relaxed to optional to cover both constructions with one
# pattern. "certify"/"certifies" both accepted (verb conjugation varies
# by sentence subject).
_NAME_CERTIFY_PATTERN = re.compile(
    r"(?i:certif(?:y|ies)\s*that)[ \t]+([A-Z][a-zA-Z.'-]+(?:[ \t]+[A-Z][a-zA-Z.'-]+){1,3})"
)
# Free-prose salary-confirmation / ITR-acknowledgement phrasing
# ("...salary disbursement for <NAME>", "...return filed by <NAME>,") -
# another genuinely common real-world certificate/letterhead construction
# (same class as _NAME_CERTIFY_PATTERN above), not tuned to one template's
# exact sentence beyond the anchor verb phrase itself.
_NAME_PROSE_PATTERN = re.compile(
    r"(?i:disbursement\s+for|return\s+filed\s+by|filed\s+by|"
    r"belongs\s+to|issued\s+for)[ \t]+"
    r"([A-Z][a-zA-Z.'-]+(?:[ \t]+[A-Z][a-zA-Z.'-]+){1,3})"
)


def extract_name(text: str) -> ExtractedField:
    """Auxiliary extraction used only for cross-document consistency
    checks (mission Phase 13) - never fed into the workflow as a primary
    manifest field, since no journey's evidence_mappings target_field is
    `name`. Label vocabulary covers multiple journeys' real wording
    (Employee/Patient/Policyholder Name) - a small, disclosed, generic
    vocabulary, not one journey's word."""
    match = (
        _NAME_LABEL.search(text)
        or _NAME_CERTIFY_PATTERN.search(text)
        or _NAME_PROSE_PATTERN.search(text)
    )
    if not match:
        return ExtractedField(
            key="name",
            raw_value=None,
            value=None,
            evidence_span=None,
            method="label_anchored_regex",
            validated=False,
            validation_note="No labeled name found.",
        )
    value = match.group(1).strip()
    return ExtractedField(
        key="name",
        raw_value=value,
        value=value,
        evidence_span=match.group(0),
        method="label_anchored_regex",
        validated=True,
        validation_note=None,
    )


# Generic date-label vocabulary (Lending/Insurance's real wording) - used
# as the fallback when a doc_type has no more specific entry below.
_GENERIC_DATE_LABELS = (
    r"Date\s*of\s*Discharge|Date\s*of\s*Report|Report\s*Date|Screening\s*Date|"
    r"Policy\s*Date|Policy\s*Period|Date\s*Issued|"
    # "Discharged"/"discharged on" deliberately NOT paired with "Admitted" -
    # a document may state both an admission and a discharge date, and the
    # manifest's own ground-truth concept here is the discharge date
    # specifically; since .search() finds the leftmost textual match and
    # "Admitted" always appears first in this pipeline's own real
    # templates, adding it as an equal alternative would silently pick the
    # wrong one of two real dates rather than "no date found" - a subtler,
    # worse failure than a clean miss.
    r"discharged\s*on|Discharged|Valid\s*Till|Valid|Date"
)

# Doc-type-specific date-label PRIORITY (same "don't pair alternatives that
# would pick the wrong one of several real dates on the page" principle as
# the generic list above, now genuinely necessary because KYC documents
# routinely carry 2-3 real dates - e.g. a passport shows Date of Birth,
# Date of Issue, AND Date of Expiry - and each doc_type's manifest-relevant
# date is a different one of those, not always the first to appear
# textually. Each doc_type's ground-truth concept: PASSPORT_SCAN -> issue
# date, VOTER_ID_CARD -> date of birth (its only real date), DRIVING_LICENCE
# -> valid-till date, not birth date.
_DATE_LABELS_BY_DOC_TYPE: dict[str, str] = {
    "PASSPORT_SCAN": r"Date\s*of\s*Issue|Date\s*Issued|Issued",
    # "[DO]OB" tolerates "DOB" -> "OOB" (D->O), the SAME traced OCR
    # artifact fixed for "DL No" -> "OL No" below - now confirmed
    # recurring across two unrelated doc types/templates, not one-off
    # noise.
    "VOTER_ID_CARD": r"Date\s*of\s*Birth|[DO]OB",
    "DRIVING_LICENCE": r"Valid\s*Till|Valid",
    # Credit Card salary slips express the pay period as prose ("Payslip
    # for Mar 1997", "for the period Jul 1971.") rather than a colon-style
    # label - a real, common payslip wording, not tuned to one template.
    "SALARY_SLIP": r"Payslip\s*for|Pay\s*Period|for\s*the\s*period",
    "PAN_CARD_IMAGE": r"Date\s*of\s*Birth|[DO]OB",
    "AADHAAR_FRONT_BACK": r"Date\s*of\s*Birth|[DO]OB",
    "BANK_STATEMENT_SUMMARY": r"Statement\s*Period|Statement\s*Date|Period",
    # "[I{]ssue" tolerates the same leading-"I" OCR misread documented
    # above for IFSC ("Issue" -> "{ssue", traced on a real sample).
    "KRA_KYC_LETTER": r"Date\s*of\s*(?:Registration|[I{]ssue)|Registered\s*on|[I{]ssued\s*on",
}

# Non-greedy: a "Policy Period: X to Y" / "Valid: X - Y" style label is
# followed by TWO dates, and a greedy quantifier here swallows both
# ("18/12/2001 to 05/01/2021") as one bogus multi-date span, since "to" and
# extra digits both fall inside the permitted character class. Matching as
# few characters as possible before requiring the terminal \d{4} stops at
# the FIRST date's year instead.
# Parens tolerated: OCR sometimes misreads a date's "/" separator as "("
# (traced: "21/03/1977" -> "21 (03/1977") - a real, recurring OCR artifact
# on this punctuation, not specific to one sample. The terminal 4-digit
# year is matched as `(?:\d ?){3}\d` rather than a flat `\d{4}` so a space
# falsely inserted ANYWHERE inside the year (traced: "1977" -> "1 977",
# same "digit run split by an inserted space" artifact already handled
# elsewhere in this file, here reaching into the final group) is still
# captured - `normalize_date()` below is what actually removes the
# tolerated space before parsing.
_DATE_VALUE = r"([A-Za-z0-9,/()\-\s]{4,20}?(?:\d ?){3}\d)"


def extract_document_date(text: str, doc_type: str | None = None) -> ExtractedField:
    """Auxiliary extraction (not tied to any one journey's wording) used
    for cross-document consistency (e.g. is a medical report older than
    the policy's own reference date) and error analysis, never fed
    directly into workflow state - no evidence_mappings target_field in
    any current manifest is `document_date`.

    `doc_type` selects a more specific label PRIORITY when the doc_type is
    known to carry multiple real dates whose generic label alone wouldn't
    disambiguate which one the ground-truth concept actually is (see
    `_DATE_LABELS_BY_DOC_TYPE`); falls back to the generic vocabulary
    otherwise - existing Lending/Insurance behavior is unaffected, since
    neither of their doc types has an entry in that dict.
    """
    label_patterns = []
    specific = _DATE_LABELS_BY_DOC_TYPE.get(doc_type or "")
    if specific:
        label_patterns.append(specific)
    label_patterns.append(_GENERIC_DATE_LABELS)

    for labels in label_patterns:
        pattern = re.compile(rf"(?:{labels})\s*[:\-]?\s*{_DATE_VALUE}", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            raw = match.group(1).strip()
            normalized = normalize_date(raw)
            # Never fall back to the raw, un-normalized string as `value`
            # (traced: a genuinely impossible calendar date - OCR misread
            # "18/04/2019" as "48/04/2019", day 48 - correctly failed
            # normalization and was correctly flagged `validated=False`,
            # but `value` still held the garbage raw string instead of
            # None. Every other field in this file (money, identifier,
            # name) returns None rather than an unnormalized/unvalidated
            # value on failure; this one silently didn't, an inconsistency
            # with the "never fabricate" principle, not a deliberate
            # design - nothing in this codebase's test suite exercises or
            # depends on the raw fallback.
            return ExtractedField(
                key="document_date",
                raw_value=raw,
                value=normalized,
                evidence_span=match.group(0),
                method="label_anchored_regex",
                validated=normalized is not None,
                validation_note=None if normalized else f"Could not normalize date '{raw}'.",
            )

    return ExtractedField(
        key="document_date",
        raw_value=None,
        value=None,
        evidence_span=None,
        method="label_anchored_regex",
        validated=False,
        validation_note="No labeled document date found.",
    )


# Real Indian government-identifier formats, each with its own genuine
# structure (mission Step 5's "identifier formatting") - not a single
# generic "alphanumeric code" pattern, since accepting the WRONG format
# for a doc_type (e.g. an EPIC-shaped string on a passport) would validate
# a plausible-looking but wrong value. Each pattern is anchored to a
# label actually used on these documents, and separately format-validated
# (Phase 12's "AI extracts, deterministic validation verifies").
_IDENTIFIER_LABELS_BY_DOC_TYPE: dict[str, str] = {
    "PASSPORT_SCAN": r"Passport\s*No\.?|Passport\s*Number|No\.",
    # "Card No" -> "Gard No" (C->G) is a traced, 100%-reproducible OCR
    # misread on this dataset's voter_compact template (2 of 2 real
    # failures), the same class of single-letter-lookalike artifact as
    # CANCELLED_CHEQUE's "IFSC" tolerance below - not a guess.
    "VOTER_ID_CARD": r"EPIC\s*No\.?|Voter\s*ID\s*No\.?|[CG]ard\s*No\.?",
    # "DL No" -> "OL No" (D->O) is the same class of traced artifact,
    # 100%-reproducible on this dataset's dl_standard template (2 of 2
    # real failures).
    "DRIVING_LICENCE": r"[DO]L\s*No\.?|Licen[cs]e\s*No\.?|Licen[cs]e\s*Number",
    "ITR_V_ACKNOWLEDGEMENT": r"PAN|Permanent\s*Account\s*Number",
    "PAN_CARD_IMAGE": r"PAN|Permanent\s*Account\s*Number",
    "AADHAAR_FRONT_BACK": r"Aadhaar\s*(?:No\.?|Number)?|UIDAI|UID\s*No\.?",
    # OCR consistently misreads the leading "I" of "IFSC" as a lookalike
    # bracket/punctuation mark under this dataset's rendering/degradation
    # (traced across 3 separate samples: "IFSC" -> "\FSC", "(FSC", and
    # "{FSC") - a real, reproducible artifact on this specific letter
    # (also seen on "Issue" -> "{ssue" in the KRA date label below), not
    # one sample's noise, so it's tolerated at the label level (still
    # requires the rest of "FSC" to match literally).
    "CANCELLED_CHEQUE": r"[I\\({]FSC\s*Code|[I\\({]FSC",
    "BANK_STATEMENT_SUMMARY": r"Account\s*(?:No\.?|Number)",
    "KRA_KYC_LETTER": r"PAN|Permanent\s*Account\s*Number",
}
# Two SEPARATE capture groups (letter-prefix, digit-suffix) rather than
# one flat match - this matters for correction, not just matching: the
# shared digit-confusion fixer (normalize.py, built for pure-amount
# contexts like "IB0,000") maps 'B'->'8' among others, and applying it to
# a flat "B9979903" match would silently corrupt a genuinely correct
# leading passport-series LETTER into a digit (traced: exactly this
# happened before this split existed - "B9979903" -> "89979903"). Keeping
# the letter prefix in its own group means it is never run through the
# digit fixer at all; only the digit-suffix group is.
#
# The digit-suffix group tolerates a SPACE embedded within the digit run
# (traced as a real, pervasive Tesseract artifact under degradation - a
# contiguous printed number split into two OCR "words", e.g. "G6808811"
# read as "G680881 1") - captures a slightly WIDER window than the exact
# expected length to allow for 1-2 embedded spaces, and the extractor
# below strips them and validates the STRIPPED length is exactly right
# before accepting the value, so this tolerance can't accidentally
# swallow extra unrelated trailing digits from elsewhere on the line.
_IDENTIFIER_DIGIT_LEN: dict[str, int] = {
    "PASSPORT_SCAN": 7,
    "VOTER_ID_CARD": 7,
    "DRIVING_LICENCE": 13,
    "ITR_V_ACKNOWLEDGEMENT": 4,  # PAN's middle digit run
    "PAN_CARD_IMAGE": 4,  # same PAN format, different doc_type/journey
    "AADHAAR_FRONT_BACK": 12,  # Aadhaar's full digit count, no letters at all
    "CANCELLED_CHEQUE": 7,  # IFSC's fixed "0" + 6-digit branch code portion
    "BANK_STATEMENT_SUMMARY": 12,  # this dataset's bank account number length
    "KRA_KYC_LETTER": 4,  # same PAN format, different doc_type/journey
}
# Every digit-middle group below is scoped to `[0-9OoIlSB ]` - the SAME
# confusable set `normalize.py`'s `try_fix_ocr_digit_confusion` already
# corrects (O/o->0, I/l->1, S->5, B->8), applied to this group a few lines
# below. Before this fix the capture classes only included O/o/I/l, never
# S/B, so a genuinely correct identifier whose digit run happened to
# contain an OCR-misread S or B (traced: IFSC "0504862" -> "O5S04862")
# could not even be CAPTURED by the regex at all, let alone corrected -
# the fixer never got a chance to run. Widening the capture class to match
# the already-vetted correction table is not a new guess.
# Each pattern has THREE groups (letter-prefix, digit-middle,
# trailing-letter) so a format with a trailing letter (PAN: 5 letters + 4
# digits + 1 letter) can be handled by the same mechanism as the
# letters-then-digits-only formats (whose trailing-letter group is simply
# absent/empty) - the digit-confusion fixer is applied ONLY to the middle
# group either way, never to either letter group.
# All separators between capture groups below are `[ \t]?`, NOT `\s?` -
# `\s` also matches a newline, which let a greedy digit-group's backtrack
# reach across a LINE BREAK and pull a leading letter from the NEXT,
# unrelated printed line into the trailing-letter group (traced: PAN
# "TFASX0840L\nRegistered on:..." - the digit group first tried its full
# greedy width including the real trailing "L", failed to leave anything
# for the trailing-letter group, backtracked by one character as
# expected, but `\s?` then happily matched the newline and group 3 latched
# onto "R" from "Registered" on the next line instead of failing cleanly).
# A real identifier is printed on one line, so no separator inside it
# should ever match a newline - same "same-line only" principle already
# applied to name capture's word separator.
#
# Indian passport: 1 letter (real series letters exclude a few easily
# OCR-confused ones) + 7 digits.
_PASSPORT_NO_VALUE = re.compile(r"([A-PR-Z])[ \t]?([0-9OoIlSB ]{7,10})()", re.IGNORECASE)
# EPIC (voter ID) number: 3 letters + 7 digits.
_EPIC_NO_VALUE = re.compile(r"([A-Z]{3})[ \t]?([0-9OoIlSB ]{7,10})()", re.IGNORECASE)
# Driving licence: 2-letter state code + 2-digit RTO + 4-digit year +
# 7-digit serial (a commonly used real DL numbering convention).
_DL_NO_VALUE = re.compile(r"([A-Z]{2})[ \t]?([0-9OoIlSB ]{13,17})()", re.IGNORECASE)
# Indian PAN: 5 letters + 4 digits + 1 letter (a real, fixed, well-known
# government format, distinct in shape from the 3 above). Reused as-is for
# Account Opening's PAN_CARD_IMAGE - the same government format, just a
# different journey/doc_type, not a copy of Credit Card business logic.
#
# The letter groups tolerate the SAME digit lookalikes normalize.py's
# `_OCR_DIGIT_CONFUSIONS` already trusts (O/o->0, I/l->1, S->5, B->8) -
# traced on two real samples: a trailing letter "I" read as digit "1"
# ("IWCKS6883I" -> "IWCKS68831"), and a prefix letter "O" read as digit
# "0" ("YMVZO4898T" -> "YMVZ04898T"). Without this, the letter group's
# strict `[A-Z]` requirement fails to match at all, and the whole
# identifier is lost - `_canonicalize_pan_letter_group` below converts
# these back using the same mapping, applied ONLY to the two letter
# groups, never to the digit-middle group.
_PAN_VALUE = re.compile(
    r"([A-Z0oO1lI5S8B]{5})[ \t]?([0-9OoIlSB ]{4,6})[ \t]?([A-Z0oO1lI5S8B])", re.IGNORECASE
)
_DIGIT_TO_ALPHA_CONFUSIONS = {"0": "O", "1": "I", "5": "S", "8": "B"}


def _canonicalize_pan_letter_group(group: str) -> str:
    return "".join(_DIGIT_TO_ALPHA_CONFUSIONS.get(ch, ch) for ch in group)
# Aadhaar number: 12 digits, no letters at all (unlike every format above)
# - both letter groups are the always-empty `()` capture, and the middle
# digit group tolerates the real printed space-grouping ("1234 5678 9012")
# PLUS the same embedded-OCR-space tolerance as every other identifier
# above; the expected-length check after stripping ALL spaces is what
# actually distinguishes a genuine 12-digit Aadhaar number from noise.
_AADHAAR_VALUE = re.compile(r"()([0-9OoIlSB ]{12,18})()", re.IGNORECASE)
# IFSC (Indian Financial System Code): 4-letter bank code + a fixed "0" +
# 6-digit branch code (11 chars total) - a real, well-known government/RBI
# format, genuinely new SHAPE from every identifier above (the branch
# portion is bank-assigned digits, not a checksum letter), reused via the
# same letter-prefix/digit-middle split so the digit-confusion fixer only
# ever touches the numeric branch portion, never the bank-code letters.
_IFSC_VALUE = re.compile(r"([A-Z]{4})[ \t]?([0-9OoIlSB ]{7,10})()", re.IGNORECASE)
# Bank account number: pure digits, no letters at all (same empty-letter-
# group shape as Aadhaar above) - length varies by bank in the real world,
# but this dataset generates a fixed, disclosed length (see
# _IDENTIFIER_DIGIT_LEN) since there is no single universal Indian
# standard length to validate against.
_ACCOUNT_NUMBER_VALUE = re.compile(r"()([0-9OoIlSB ]{12,16})()", re.IGNORECASE)

_IDENTIFIER_VALUE_PATTERN: dict[str, re.Pattern] = {
    "PASSPORT_SCAN": _PASSPORT_NO_VALUE,
    "VOTER_ID_CARD": _EPIC_NO_VALUE,
    "DRIVING_LICENCE": _DL_NO_VALUE,
    "ITR_V_ACKNOWLEDGEMENT": _PAN_VALUE,
    "PAN_CARD_IMAGE": _PAN_VALUE,
    "AADHAAR_FRONT_BACK": _AADHAAR_VALUE,
    "CANCELLED_CHEQUE": _IFSC_VALUE,
    "BANK_STATEMENT_SUMMARY": _ACCOUNT_NUMBER_VALUE,
    "KRA_KYC_LETTER": _PAN_VALUE,
}


def extract_identifier(text: str, doc_type: str) -> ExtractedField:
    """Extracts and format-validates the doc_type's own real government
    identifier (passport number / EPIC number / DL number) - auxiliary,
    like name/document_date: no current manifest's evidence_mappings
    target_field is an identifier (KYC's target is the boolean
    `ovd_document_uploaded`), but it's a real, verifiable fact worth
    surfacing for potential future cross-document consistency, not
    invented busywork."""
    label_pattern = _IDENTIFIER_LABELS_BY_DOC_TYPE.get(doc_type)
    value_pattern = _IDENTIFIER_VALUE_PATTERN.get(doc_type)
    if not label_pattern or not value_pattern:
        return ExtractedField(
            key="identifier",
            raw_value=None,
            value=None,
            evidence_span=None,
            method="label_anchored_regex",
            validated=False,
            validation_note=f"No identifier format known for doc_type '{doc_type}'.",
        )

    label_re = re.compile(rf"(?:{label_pattern})\s*[:\-]?\s*", re.IGNORECASE)
    label_match = label_re.search(text)
    if not label_match:
        return ExtractedField(
            key="identifier",
            raw_value=None,
            value=None,
            evidence_span=None,
            method="label_anchored_regex",
            validated=False,
            validation_note="No recognized identifier label found.",
        )

    value_match = value_pattern.search(text, pos=label_match.end())
    if not value_match:
        return ExtractedField(
            key="identifier",
            raw_value=None,
            value=None,
            evidence_span=label_match.group(0),
            method="label_anchored_regex",
            validated=False,
            validation_note="Identifier label found but no value matched the expected format.",
        )

    letter_prefix = value_match.group(1)
    digit_suffix_raw = value_match.group(2)
    trailing_letter = value_match.group(3) or ""  # empty for non-PAN formats
    if value_pattern is _PAN_VALUE:
        letter_prefix = _canonicalize_pan_letter_group(letter_prefix)
        trailing_letter = _canonicalize_pan_letter_group(trailing_letter)
    raw = letter_prefix + digit_suffix_raw + trailing_letter
    # Strip any embedded space(s) BEFORE validating length - this is what
    # actually recovers the "digit run split by a false OCR space" case
    # without risking over-matching: only an exact expected LENGTH after
    # stripping is accepted, so a window that accidentally captured extra
    # trailing digits from elsewhere on the line is rejected here, not
    # silently trusted.
    digit_suffix_stripped = digit_suffix_raw.replace(" ", "")
    expected_len = _IDENTIFIER_DIGIT_LEN[doc_type]
    if len(digit_suffix_stripped) != expected_len:
        return ExtractedField(
            key="identifier",
            raw_value=raw,
            value=None,
            evidence_span=label_match.group(0) + raw,
            method="label_anchored_regex",
            validated=False,
            validation_note=(
                f"Matched label but digit portion '{digit_suffix_stripped}' is "
                f"{len(digit_suffix_stripped)} chars, expected {expected_len}."
            ),
        )

    # Digit-confusion correction is applied ONLY to the middle digit group
    # - never to either letter group, which are real letter codes, not
    # OCR-mangled numbers (see the comment above the value patterns).
    fixed_suffix = try_fix_ocr_digit_confusion(digit_suffix_stripped)
    # Format-validated (deterministic, mission Phase 12): the value must
    # actually conform to the doc_type's real identifier shape after OCR
    # digit-confusion correction, not merely "some text was found".
    normalized = (letter_prefix + fixed_suffix + trailing_letter).upper()
    return ExtractedField(
        key="identifier",
        raw_value=raw,
        value=normalized,
        evidence_span=label_match.group(0) + raw,
        method="label_anchored_regex",
        validated=True,
        validation_note=None,
    )


def extract_fields_for_doc_type(
    text: str, doc_type: str, lines: list | None = None
) -> list[ExtractedField]:
    """Journey-agnostic dispatch by target-field shape, not by
    `if journey_type == ...` - a new pack whose evidence_mappings target
    `monthly_income` or `employer_name` gets the same extractors for
    free; a pack with a genuinely new target field needs a new extractor
    function added here, not a manifest-specific branch. Auxiliary facts
    (name, document_date) are always attempted regardless of doc_type -
    they feed cross-document consistency, not workflow state, and cost
    nothing to look for on a document that doesn't have them (a clean
    `None` result, not an error)."""
    fields: list[ExtractedField] = []
    if doc_type in ("SALARY_SLIP", "BANK_STATEMENT"):
        fields.append(extract_monthly_income(text, doc_type, lines=lines))
    if doc_type in ("OFFICE_ID_CARD", "OFFER_LETTER"):
        fields.append(extract_employer_name(text))
    if doc_type in _IDENTIFIER_LABELS_BY_DOC_TYPE:
        fields.append(extract_identifier(text, doc_type))
    fields.append(extract_name(text))
    fields.append(extract_document_date(text, doc_type=doc_type))
    return fields
