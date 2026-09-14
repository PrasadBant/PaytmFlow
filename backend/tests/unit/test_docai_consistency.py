from app.docai.consistency import (
    check_identifier_consistency,
    check_income_consistency,
    check_name_consistency,
)


class TestIncomeConsistency:
    def test_close_values_no_conflict(self):
        # Within the 10% tolerance band.
        assert check_income_consistency(85000, 88000) is None

    def test_far_apart_values_flagged(self):
        finding = check_income_consistency(85000, 30000)
        assert finding is not None
        assert finding.is_conflict
        assert finding.field == "monthly_income"

    def test_missing_existing_value_no_conflict(self):
        assert check_income_consistency(None, 85000) is None

    def test_missing_new_value_no_conflict(self):
        assert check_income_consistency(85000, None) is None


class TestNameConsistency:
    def test_matching_names_no_conflict(self):
        assert check_name_consistency("Marc Estrada", "marc estrada") is None

    def test_different_names_flagged(self):
        finding = check_name_consistency("Marc Estrada", "Julie Harris")
        assert finding is not None
        assert finding.is_conflict
        assert finding.field == "name"

    def test_missing_values_no_conflict(self):
        assert check_name_consistency(None, "Marc Estrada") is None
        assert check_name_consistency("Marc Estrada", None) is None

    def test_whitespace_only_difference_no_conflict(self):
        assert check_name_consistency("Srija  Uppuluri", "Srija Uppuluri") is None

    def test_case_only_difference_no_conflict(self):
        assert check_name_consistency("SRIJA UPPULURI", "Srija Uppuluri") is None

    def test_initial_stands_in_for_full_token(self):
        assert check_name_consistency("Marc Estrada", "Marc E. Estrada") is None


class TestIdentifierConsistency:
    def test_matching_identifiers_no_conflict(self):
        assert check_identifier_consistency("ABCDE1234F", "ABCDE1234F") is None

    def test_case_difference_no_conflict(self):
        # Extractors already normalize to uppercase, but the comparison
        # itself should not depend on that - defense in depth.
        assert check_identifier_consistency("abcde1234f", "ABCDE1234F") is None

    def test_whitespace_difference_no_conflict(self):
        assert check_identifier_consistency(" ABCDE1234F ", "ABCDE1234F") is None

    def test_genuinely_different_identifiers_flagged(self):
        finding = check_identifier_consistency("ABCDE1234F", "ZZZZZ9999Z")
        assert finding is not None
        assert finding.is_conflict
        assert finding.field == "identifier"

    def test_no_fuzzy_tolerance_even_for_one_character_difference(self):
        # Deliberately NOT fuzzy, unlike names - a single differing
        # character means a genuinely different identifier, not a
        # formatting variant. "Do not use fuzzy matching so aggressively
        # that genuinely different identities become equal."
        finding = check_identifier_consistency("ABCDE1234F", "ABCDE1234G")
        assert finding is not None
        assert finding.is_conflict

    def test_missing_values_no_conflict(self):
        assert check_identifier_consistency(None, "ABCDE1234F") is None
        assert check_identifier_consistency("ABCDE1234F", None) is None
