from app.docai.normalize import (
    names_match,
    normalize_date,
    normalize_indian_amount,
    try_fix_ocr_digit_confusion,
)


class TestNormalizeIndianAmount:
    def test_symbol_prefixed(self):
        assert normalize_indian_amount("₹85,000") == 85000

    def test_rs_dot_prefixed(self):
        assert normalize_indian_amount("Rs. 1,25,000") == 125000

    def test_inr_prefixed(self):
        assert normalize_indian_amount("INR 85000") == 85000

    def test_plain_indian_grouping(self):
        assert normalize_indian_amount("12,50,000") == 1250000

    def test_paise_fragment_dropped(self):
        assert normalize_indian_amount("₹85,000.50") == 85000

    def test_unparseable_returns_none(self):
        assert normalize_indian_amount("not a number") is None

    def test_empty_returns_none(self):
        assert normalize_indian_amount("") is None


class TestOcrDigitConfusionFix:
    def test_fixes_within_numeric_token(self):
        # 'O'->'0', 'I'/'l'->'1', 'S'->'5' only inside an otherwise
        # digit/punctuation/confusable-letter token.
        assert try_fix_ocr_digit_confusion("₹8O,OOO") == "₹80,000"

    def test_does_not_mangle_real_words(self):
        text = "Net Pay for Islam Solutions"
        assert try_fix_ocr_digit_confusion(text) == text


class TestNormalizeDate:
    def test_slash_format(self):
        assert normalize_date("15/03/2024") == "2024-03-15"

    def test_month_year(self):
        assert normalize_date("Mar 2024") == "2024-03"

    def test_unrecognized_returns_none(self):
        assert normalize_date("not-a-date") is None


class TestNamesMatch:
    def test_exact_match(self):
        assert names_match("Marc Estrada", "Marc Estrada")

    def test_case_and_spacing_insensitive(self):
        assert names_match("marc   estrada", "Marc Estrada")

    def test_initial_tolerant(self):
        assert names_match("Marc Estrada", "M Estrada")

    def test_genuinely_different_names_do_not_match(self):
        assert not names_match("Marc Estrada", "Julie Harris")
