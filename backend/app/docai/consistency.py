"""Cross-document consistency checking (mission Phase 13).

Compares a newly-extracted field against values already recorded from
OTHER evidence documents in the same journey. This is deterministic
comparison code, not a model - "does document B roughly agree with
document A" is a well-defined equality/tolerance check once both values
have been normalized, not something that benefits from being learned.

This module never decides workflow state. It returns a plain
`ConsistencyFinding` that the caller (app/ai/local_ml.py) turns into an
`AIConflict` in the existing, unchanged `AIInterpretationResult` shape -
the deterministic engine downstream still makes the actual NEEDS_REVIEW
decision (via the existing ambiguity_rules / conflicts mechanism), exactly
as it already does for MockAI/LLMProvider conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.docai.normalize import names_match

# How far two independently-reported income figures may differ (as a
# fraction of the larger one) before being flagged as a real conflict
# rather than benign rounding/variance between a salary slip and a bank
# credit (e.g. minor deductions differences). This is a documented
# design threshold, not a measured statistic.
INCOME_TOLERANCE_FRACTION = 0.10


@dataclass
class ConsistencyFinding:
    is_conflict: bool
    field: str
    message: str
    existing_value: object
    new_value: object


def check_income_consistency(
    existing_income: int | None, new_income: int | None
) -> ConsistencyFinding | None:
    if existing_income is None or new_income is None:
        return None
    if existing_income == 0:
        return None
    diff_fraction = abs(existing_income - new_income) / max(existing_income, new_income)
    if diff_fraction <= INCOME_TOLERANCE_FRACTION:
        return None
    return ConsistencyFinding(
        is_conflict=True,
        field="monthly_income",
        message=(
            f"Previously recorded monthly income (₹{existing_income:,}) differs from this "
            f"document's monthly income (₹{new_income:,}) by more than "
            f"{int(INCOME_TOLERANCE_FRACTION * 100)}%."
        ),
        existing_value=existing_income,
        new_value=new_income,
    )


def check_name_consistency(
    existing_name: str | None, new_name: str | None
) -> ConsistencyFinding | None:
    if not existing_name or not new_name:
        return None
    if names_match(existing_name, new_name):
        return None
    return ConsistencyFinding(
        is_conflict=True,
        field="name",
        message=(
            f"The name on this document ('{new_name}') does not match the name already "
            f"recorded from a previous document ('{existing_name}')."
        ),
        existing_value=existing_name,
        new_value=new_name,
    )


def check_identifier_consistency(
    existing_identifier: str | None, new_identifier: str | None
) -> ConsistencyFinding | None:
    """Exact-match comparison only, deliberately no fuzzy tolerance - unlike
    a person's name (which legitimately varies in casing/spacing/initials
    across documents), a government identifier is either the same code or
    it is a genuinely different one; treating two different identifiers
    as "close enough" would be exactly the "fuzzy matching so aggressive
    that genuinely different identities become equal" failure mode the
    cross-document-consistency phase explicitly warns against.

    The CALLER is responsible for only ever comparing two identifiers
    extracted from the SAME doc_type (see app/ai/local_ml.py) - this
    function has no way to know on its own whether two identifier
    strings are even the same FORMAT (a PAN and an IFSC code are both
    "identifiers" but comparing them would be meaningless), so doc_type
    scoping happens one layer up, not here.
    """
    if not existing_identifier or not new_identifier:
        return None
    existing_norm = existing_identifier.strip().upper()
    new_norm = new_identifier.strip().upper()
    if existing_norm == new_norm:
        return None
    return ConsistencyFinding(
        is_conflict=True,
        field="identifier",
        message=(
            f"The identifier on this document ('{new_identifier}') does not match the "
            f"identifier already recorded from a previous document of the same type "
            f"('{existing_identifier}')."
        ),
        existing_value=existing_identifier,
        new_value=new_identifier,
    )


def check_salary_slip_internal_consistency(
    gross_income: int | None, total_deductions: int | None, net_income: int | None
) -> ConsistencyFinding | None:
    """Verifies that the salary slip's internal arithmetic (Gross - Deductions == Net)
    is consistent.
    """
    if gross_income is None or total_deductions is None or net_income is None:
        return None
    if gross_income <= 0:
        return None
    expected_net = gross_income - total_deductions
    if expected_net <= 0:
        return None
    if expected_net != net_income:
        return ConsistencyFinding(
            is_conflict=True,
            field="monthly_income",
            message=(
                f"Document internal calculation conflict: Gross Earnings (₹{gross_income:,}) "
                f"minus Total Deductions (₹{total_deductions:,}) equals ₹{expected_net:,}, "
                f"which conflicts with stated Net Pay (₹{net_income:,})."
            ),
            existing_value=expected_net,
            new_value=net_income,
        )
    return None

