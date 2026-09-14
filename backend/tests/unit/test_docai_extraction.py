from app.docai.extraction import (
    extract_document_date,
    extract_employer_name,
    extract_fields_for_doc_type,
    extract_identifier,
    extract_monthly_income,
    extract_name,
)
from app.docai.ocr import OcrLine


class TestExtractMonthlyIncomeSalarySlip:
    def test_net_pay_label(self):
        text = "Basic Pay 50,000\nNet Pay ₹85,000"
        field = extract_monthly_income(text, "SALARY_SLIP")
        assert field.value == 85000
        assert field.validated

    def test_take_home_synonym_label(self):
        text = "Employee: X\nTake Home: Rs. 1,25,000"
        field = extract_monthly_income(text, "SALARY_SLIP")
        assert field.value == 125000

    def test_no_label_returns_none_not_fabricated(self):
        text = "Some unrelated document text with a number 85000 in it."
        field = extract_monthly_income(text, "SALARY_SLIP")
        assert field.value is None
        assert field.validation_note is not None

    def test_implausible_amount_is_not_validated(self):
        # 3+ digits (meets the amount-token's minimum length) but well
        # below the plausible-monthly-income floor.
        text = "Net Pay ₹999"
        field = extract_monthly_income(text, "SALARY_SLIP")
        assert field.value == 999
        assert not field.validated  # extracted, but flagged as implausible


class TestExtractMonthlyIncomeBankStatement:
    def test_same_line_label_with_intervening_text(self):
        text = "Oct 2025 SALARY CREDIT ACME TECHNOLOGIES PVT LTD 1,59,000"
        field = extract_monthly_income(text, "BANK_STATEMENT")
        assert field.value == 159000

    def test_row_band_recovers_amount_on_separate_ocr_line(self):
        # Regression: label and amount split into different OCR line
        # blocks (a real, observed Tesseract page-segmentation behavior
        # on wide two-column layouts) but at nearly the same vertical
        # position - must still be associated via line boxes, not miss
        # entirely or grab an unrelated bare number (e.g. a year).
        text = "Oct 2025 SALARY CREDIT ACME TECHNOLOGIES\n1,59,000"
        lines = [
            OcrLine(text="Oct 2025 SALARY CREDIT ACME TECHNOLOGIES", top=359, bottom=383),
            OcrLine(text="1,59,000", top=352, bottom=369),
        ]
        field = extract_monthly_income(text, "BANK_STATEMENT", lines=lines)
        assert field.value == 159000

    def test_prefers_comma_marked_amount_over_bare_year_on_same_line(self):
        text = "Oct 2025 SALARY CREDIT ACME 2025 1,59,000"
        field = extract_monthly_income(text, "BANK_STATEMENT")
        assert field.value == 159000

    def test_narration_code_label_tolerates_l_to_u_ocr_misread(self):
        # Regression: traced a real unseen-template failure where Tesseract
        # consistently read "SAL/<company>" as "SAU/<company>" (an L->U
        # letter misread under degradation) - the label must still match
        # once the separator itself survives OCR.
        text = "Oct 2025 SAU/ACME TECHNOLOGIES 1,59,000"
        field = extract_monthly_income(text, "BANK_STATEMENT")
        assert field.value == 159000

    def test_narration_code_label_still_requires_a_separator(self):
        # The L->U tolerance above must NOT degrade into "sal"/"sau"
        # matching as a bare substring prefix of any unrelated word -
        # that would trade one narrow OCR failure for false positives on
        # real (non-narration-code) content. No separator survives here,
        # so this must still safely report "not found", not a guess.
        text = "Oct 2025 SAUNELSON-MORAN TECHNOLOGIES PVT 1,59,000"
        field = extract_monthly_income(text, "BANK_STATEMENT")
        assert field.value is None


class TestExtractEmployerName:
    def test_pvt_ltd_suffix(self):
        text = "Acme Technologies India Pvt Ltd\nEMPLOYEE IDENTITY CARD"
        field = extract_employer_name(text)
        assert field.value is not None
        assert "Acme" in field.value

    def test_no_suffix_returns_none(self):
        text = "Some Company\nEMPLOYEE IDENTITY CARD"
        field = extract_employer_name(text)
        assert field.value is None

    def test_private_limited_suffix(self):
        text = "Whitmore Industries Private Limited\nOFFER OF EMPLOYMENT"
        field = extract_employer_name(text)
        assert field.value is not None
        assert "Whitmore" in field.value
        assert "Private Limited" in field.value

    def test_llp_suffix(self):
        text = "Carter and Reyes Associates LLP\nEMPLOYEE IDENTITY CARD"
        field = extract_employer_name(text)
        assert field.value is not None
        assert "Carter" in field.value
        assert field.value.endswith("LLP")

    def test_bare_limited_suffix(self):
        text = "Northgate Traders Limited\nOFFER OF EMPLOYMENT"
        field = extract_employer_name(text)
        assert field.value is not None
        assert "Northgate" in field.value

    def test_different_employer_names_all_extracted(self):
        # Different real names, same suffix shape - proves the extractor
        # generalizes to arbitrary company names rather than matching one
        # specific fixture value.
        for name in [
            "Sharma Consulting Pvt Ltd",
            "Blue River Foods Pvt Ltd",
            "Iyer Textiles Pvt Ltd",
        ]:
            text = f"{name}\nEMPLOYEE IDENTITY CARD\nDesignation: Analyst"
            field = extract_employer_name(text)
            assert field.value == name, f"expected {name!r}, got {field.value!r}"

    def test_ocr_confused_pvt_ltd_still_matches_and_is_canonicalized(self):
        # "Pvt" -> "Pyt" (v/y confusion) and "Ltd" -> "Lid" (t/i confusion)
        # are real, observed OCR misreads (see extraction.py's
        # _ALPHA_OCR_CONFUSIONS) - the suffix must still be detected AND
        # normalized back to its canonical spelling.
        text = "Harrington Steel Pyt Lid\nEMPLOYEE IDENTITY CARD"
        field = extract_employer_name(text)
        assert field.value == "Harrington Steel Pvt Ltd"

    def test_multiline_employer_name_not_matched_across_lines(self):
        # A company name that wraps onto a second physical line, with the
        # legal suffix on the FIRST line and unrelated content following
        # on the next - the extractor is line-scoped (EMPLOYER_SUFFIX_PATTERN
        # does not span "\n"), so it should capture only the first line's
        # content up to the suffix rather than bleeding into the next line.
        text = "Meridian Capital Partners Pvt Ltd\nRegistered Office: Mumbai, Maharashtra"
        field = extract_employer_name(text)
        assert field.value is not None
        assert field.value == "Meridian Capital Partners Pvt Ltd"
        assert "Registered Office" not in field.value


class TestExtractFieldsForDocType:
    def test_salary_slip_only_extracts_income_and_name(self):
        # document_date is always attempted too (auxiliary, journey-agnostic -
        # see TestExtractDocumentDate below), so it's always present in the
        # key set even when the text has no labeled date and its own value
        # ends up None.
        text = "Employee Name: Marc Estrada\nNet Pay ₹85,000"
        fields = extract_fields_for_doc_type(text, "SALARY_SLIP")
        keys = {f.key for f in fields}
        assert keys == {"monthly_income", "name", "document_date"}

    def test_office_id_card_only_extracts_employer_and_name(self):
        text = "Acme Technologies Pvt Ltd\nName: Marc Estrada"
        fields = extract_fields_for_doc_type(text, "OFFICE_ID_CARD")
        keys = {f.key for f in fields}
        assert keys == {"employer_name", "name", "document_date"}


class TestExtractDocumentDate:
    def test_labeled_date_extracted_and_normalized(self):
        text = "Discharge Summary\nDate of Discharge: 15/03/2024\nDiagnosis: Appendicitis"
        field = extract_document_date(text)
        assert field.value == "2024-03-15"
        assert field.validated

    def test_no_date_label_returns_none_not_fabricated(self):
        text = "Some unrelated document text with the year 2024 in it."
        field = extract_document_date(text)
        assert field.value is None

    def test_doc_type_specific_priority_picks_the_manifest_relevant_date(self):
        # A passport shows THREE real dates (birth, issue, expiry) - the
        # doc_type-specific priority must pick the issue date, not
        # whichever date happens to appear first in reading order (birth
        # date, here).
        text = (
            "Name: Test User\nDate of Birth: 01/01/1990\n"
            "Date of Issue: 15/06/2020\nDate of Expiry: 14/06/2030"
        )
        field = extract_document_date(text, doc_type="PASSPORT_SCAN")
        assert field.value == "2020-06-15"

    def test_unknown_doc_type_falls_back_to_generic_labels(self):
        # No entry in _DATE_LABELS_BY_DOC_TYPE for this doc_type - must
        # still work via the existing generic vocabulary (Lending/
        # Insurance behavior preserved).
        text = "Report Date: 10/02/2022"
        field = extract_document_date(text, doc_type="SOME_UNKNOWN_TYPE")
        assert field.value == "2022-02-10"


class TestExtractIdentifier:
    def test_passport_number_extracted_and_validated(self):
        text = "INDIAN PASSPORT\nPassport No: M1234567\nName: Test User"
        field = extract_identifier(text, "PASSPORT_SCAN")
        assert field.value == "M1234567"
        assert field.validated

    def test_epic_number_extracted_and_validated(self):
        text = "Voter ID Card\nEPIC No: ABC1234567\nName: Test User"
        field = extract_identifier(text, "VOTER_ID_CARD")
        assert field.value == "ABC1234567"
        assert field.validated

    def test_dl_number_extracted_and_validated(self):
        text = "DRIVING LICENCE\nDL No: MH1420230012345\nName: Test User"
        field = extract_identifier(text, "DRIVING_LICENCE")
        assert field.value == "MH1420230012345"
        assert field.validated

    def test_leading_letter_is_never_digit_corrected(self):
        # Regression: the shared digit-confusion fixer maps 'B'->'8' (a
        # real, correct fix for MONETARY amounts like "IB0,000") - applying
        # it to the whole identifier used to corrupt a genuinely correct
        # leading passport-series letter "B" into "8". The letter prefix
        # must never be run through that fixer.
        text = "Passport No: B9979903\nName: Test User"
        field = extract_identifier(text, "PASSPORT_SCAN")
        assert field.value == "B9979903"

    def test_ocr_inserted_space_within_digit_run_is_tolerated(self):
        # Regression: a real, observed Tesseract artifact under
        # degradation splits a contiguous printed number into two OCR
        # "words" (e.g. "G6808811" read as "G680881 1") - must still
        # recover the correct value once stripped.
        text = "Passport Number: G680881 1\nName: Test User"
        field = extract_identifier(text, "PASSPORT_SCAN")
        assert field.value == "G6808811"

    def test_wrong_length_after_stripping_is_rejected_not_guessed(self):
        # A value that doesn't reduce to the doc_type's exact expected
        # digit count after stripping embedded spaces must be rejected,
        # not silently accepted as "close enough".
        text = "Passport No: M12345\nName: Test User"
        field = extract_identifier(text, "PASSPORT_SCAN")
        assert field.value is None
        assert not field.validated

    def test_unknown_doc_type_returns_none_not_fabricated(self):
        field = extract_identifier("Some text", "SOME_UNKNOWN_TYPE")
        assert field.value is None
        assert not field.validated

    def test_no_label_returns_none(self):
        text = "Some document with no identifier label M1234567"
        field = extract_identifier(text, "PASSPORT_SCAN")
        assert field.value is None

    def test_pan_with_trailing_letter_extracted_and_validated(self):
        # PAN's 5-letter + 4-digit + 1-letter shape is the only format
        # with a THIRD (trailing-letter) group - covered separately from
        # the letter-prefix-only formats above.
        text = "Permanent Account Number\nPAN: ABCDE1234F\nName: Test User"
        field = extract_identifier(text, "ITR_V_ACKNOWLEDGEMENT")
        assert field.value == "ABCDE1234F"
        assert field.validated

    def test_aadhaar_no_letters_extracted_and_validated(self):
        # Aadhaar is the only format with NO letters at all - both letter
        # groups are the always-empty `()` capture.
        text = "Aadhaar No: 1234 5678 9012\nName: Test User"
        field = extract_identifier(text, "AADHAAR_FRONT_BACK")
        assert field.value == "123456789012"
        assert field.validated

    def test_ifsc_letter_prefix_plus_digit_branch_extracted(self):
        text = "IFSC Code: HDFC0001234\nA/c No: 12345\nName: Test User"
        field = extract_identifier(text, "CANCELLED_CHEQUE")
        assert field.value == "HDFC0001234"
        assert field.validated

    def test_trailing_letter_group_never_crosses_a_line_break(self):
        # Significant cross-journey regression (found during the
        # Investment phase, affects EVERY identifier pattern with a
        # trailing-letter group - i.e. PAN everywhere it's used): the
        # group separators used to be `\s?`, which also matches a
        # newline. A PAN's digit group greedily tried its full width
        # (IGNORECASE folds "l" to also match "L"), had to backtrack by
        # one character to leave room for the trailing-letter group, but
        # `\s?` then happily crossed the newline and let the trailing
        # group latch onto "R" from "Registered" on the NEXT, unrelated
        # line instead of failing cleanly or finding the real "L".
        text = "Name: Marcus Ryan PAN TFASX0840L\nRegistered on: 05/09/2018"
        field = extract_identifier(text, "KRA_KYC_LETTER")
        assert field.value == "TFASX0840L"
        assert field.validated

    def test_monetary_digit_confusion_fixer_never_runs_on_identifiers_directly(self):
        # `try_fix_ocr_digit_confusion` is a MONETARY-context fixer (built
        # for amounts like "IB0,000") - it must never be handed a whole
        # identifier string. A PAN digit run containing a letter that IS
        # one of the fixer's confusable characters (e.g. 'S'->'5' is in
        # its table) must pass through extract_identifier unaltered
        # whenever it's a genuinely correct digit already, proving the
        # identifier path calls the fixer only on the isolated digit
        # group, never on letter-containing spans.
        text = "PAN: QRSTU5678V\nName: Test User"
        field = extract_identifier(text, "ITR_V_ACKNOWLEDGEMENT")
        # letter prefix "QRSTU" (contains no digit-confusable chars in a
        # position that would matter) and trailing "V" must survive
        # completely unchanged - only the digit group "5678" is ever
        # eligible for the fixer, and it's already all-digit so the
        # fixer is a no-op on it too.
        assert field.value == "QRSTU5678V"

    def test_same_identifier_shape_isolated_per_doc_type(self):
        # Cross-journey stability: PAN's exact same value pattern is
        # reused (not copied) across ITR_V_ACKNOWLEDGEMENT (Credit Card),
        # PAN_CARD_IMAGE (Account Opening), and KRA_KYC_LETTER
        # (Investment) - each must independently extract the same value
        # from equivalent text, proving the shared pattern generalizes
        # rather than being accidentally doc_type-specific.
        for doc_type in ("ITR_V_ACKNOWLEDGEMENT", "PAN_CARD_IMAGE", "KRA_KYC_LETTER"):
            text = f"PAN: ABCDE1234F\nName: Test User ({doc_type})"
            field = extract_identifier(text, doc_type)
            assert field.value == "ABCDE1234F", f"failed for {doc_type}"
            assert field.validated, f"not validated for {doc_type}"


class TestNameCrossLineRegression:
    def test_name_capture_does_not_bleed_across_a_line_break(self):
        # Regression: the name-capture group's inter-word separator used
        # to be plain \s+ (which also matches newlines), letting it
        # swallow the NEXT labeled line as if it were part of the name
        # (traced: "Tiffany Kennedy" captured as "Tiffany Kennedy\nFather's
        # Name" because "Father's" is also capitalized-word-shaped).
        text = "Elector's Name: Tiffany Kennedy\nFather's Name: John Kennedy"
        field = extract_name(text)
        assert field.value == "Tiffany Kennedy"
        assert "Father" not in field.value


class TestLabelMatchingSafety:
    """Dedicated label-substring false-positive audit (integrity-hardening
    phase, mission Step 4). Every short/bare label word in `_NAME_LABEL`
    is a substring-match risk inside an unrelated ALL-CAPS word, since
    the capture group's only real anchor is "next char is uppercase" -
    which an ALL-CAPS word trivially satisfies too."""

    def test_pay_label_does_not_match_inside_payroll(self):
        # Regression: found DURING this project's own regression-checking
        # discipline (caught before ever being reported, not after) - a
        # bare "Pay" label substring-matched inside Credit Card's
        # "PAYROLL DEPARTMENT" header, and the capture group happily
        # accepted "ROLL DEPARTMENT" as a fabricated name since both
        # words are Title-Case-shaped (in this case, all-caps, which
        # still satisfies `[A-Z][a-zA-Z.'-]+`).
        text = "PAYROLL DEPARTMENT\nGutierrez-Pruitt Industries Ltd"
        field = extract_name(text)
        assert field.value is None or "ROLL" not in (field.value or "")

    def test_pay_label_still_matches_a_real_standalone_use(self):
        # The `\b` fix must not be so strict it breaks the real case it
        # was added for.
        text = "Pay: Patrick Thompson\nCANCELLED"
        field = extract_name(text)
        assert field.value == "Patrick Thompson"

    def test_name_label_does_not_match_inside_surname(self):
        # "Name" is an even more common short label - check it isn't
        # swallowing itself out of a longer real word either, using the
        # same construction (a longer ALL-CAPS/Title-Case word starting
        # with the label text, immediately followed by more real
        # content).
        text = "SURNAME REGISTRY\nJohn Smith"
        field = extract_name(text)
        # "Name" has no \b guard (unlike "Pay"), so this documents
        # CURRENT behavior rather than asserting a guarantee - "SURNAME"
        # begins with "S", not "Name", so the literal substring "Name"
        # cannot appear inside it at all; this is a no-op case included
        # to make the boundary explicit rather than assumed.
        assert "SUR" not in (field.value or "")

    def test_billed_to_label_matches_real_utility_bill_construction(self):
        text = "OFFICE OF THE ELECTRICITY SUPPLY BOARD\nBilled to: Eric Goodwin"
        field = extract_name(text)
        assert field.value == "Eric Goodwin"
