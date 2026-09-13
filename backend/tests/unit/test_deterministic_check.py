from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.deterministic_check import (
    DeterministicCheckError,
    deterministic_check,
)
from app.core.models import (
    CheckToken,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.rules import derive_field_states
from app.packs.registry import pack_registry
from app.schemas.enums import ErrorCode, JourneyType


def get_lending_initial_snapshot():
    pack_registry.load_all()
    pack = pack_registry.get_pack(JourneyType.LENDING)
    assert pack is not None

    v1_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
    }
    v1_states, _ = derive_field_states(pack, v1_values)
    snap = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields=v1_states,
        goal={"loan_amount": 200000, "tenure_months": 24},
    )
    return snap, pack


def test_deterministic_check_success():
    snap, pack = get_lending_initial_snapshot()
    fixed_time = datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC)

    token = deterministic_check(
        snapshot=snap,
        expected_snapshot_id=snap.snapshot_id,
        action_id="UPLOAD_INCOME_PROOF",
        action_input={"monthly_income": 85000},
        manifest=pack,
        now=fixed_time,
    )

    assert isinstance(token, CheckToken)
    assert token.journey_id == snap.journey_id
    assert token.journey_type == "LENDING"
    assert token.action_id == "UPLOAD_INCOME_PROOF"
    assert token.previous_snapshot_id == snap.snapshot_id
    assert token.direct_fields == ["monthly_income"]
    assert token.new_values == {"monthly_income": 85000}
    assert token.created_at == fixed_time


def test_deterministic_check_rejects_stale_snapshot():
    snap, pack = get_lending_initial_snapshot()
    stale_id = uuid4()

    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=stale_id,
            action_id="UPLOAD_INCOME_PROOF",
            action_input={"monthly_income": 85000},
            manifest=pack,
        )

    err = exc_info.value
    assert err.code == ErrorCode.ACTION_STALE
    assert str(err.details["current_snapshot_id"]) == str(snap.snapshot_id)
    assert str(err.details["expected_snapshot_id"]) == str(stale_id)


def test_deterministic_check_rejects_unknown_action():
    snap, pack = get_lending_initial_snapshot()

    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=snap.snapshot_id,
            action_id="NON_EXISTENT_ACTION_XYZ",
            action_input={},
            manifest=pack,
        )

    err = exc_info.value
    assert err.code == ErrorCode.ACTION_INVALID
    assert "NON_EXISTENT_ACTION_XYZ" in err.message


def test_deterministic_check_rejects_failed_preconditions():
    snap, pack = get_lending_initial_snapshot()

    # ACCEPT_LOAN_TERMS requires monthly_income and employer_name, which are blocked in v1
    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=snap.snapshot_id,
            action_id="ACCEPT_LOAN_TERMS",
            action_input={"accept_terms": True},
            manifest=pack,
        )

    err = exc_info.value
    assert err.code == ErrorCode.ACTION_INVALID
    assert "failed_precondition" in err.details


def test_deterministic_check_rejects_missing_required_input():
    snap, pack = get_lending_initial_snapshot()

    # SUBMIT_EMPLOYMENT_INFO has precondition kyc_verified (satisfied), but requires employment_type
    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=snap.snapshot_id,
            action_id="SUBMIT_EMPLOYMENT_INFO",
            action_input={},  # Missing required employment_type
            manifest=pack,
        )

    err = exc_info.value
    assert err.code == ErrorCode.VALIDATION_ERROR
    assert err.details["missing_field"] == "employment_type"


def test_deterministic_check_rejects_invalid_enum_option():
    snap, pack = get_lending_initial_snapshot()

    with pytest.raises(DeterministicCheckError) as exc_info:
        deterministic_check(
            snapshot=snap,
            expected_snapshot_id=snap.snapshot_id,
            action_id="SUBMIT_EMPLOYMENT_INFO",
            action_input={"employment_type": "INVALID_JOB_CATEGORY"},
            manifest=pack,
        )

    err = exc_info.value
    assert err.code == ErrorCode.VALIDATION_ERROR
    assert "allowed_values" in err.details


def test_deterministic_check_purity_100_runs():
    snap, pack = get_lending_initial_snapshot()
    fixed_time = datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC)

    first_token = deterministic_check(
        snapshot=snap,
        expected_snapshot_id=snap.snapshot_id,
        action_id="UPLOAD_INCOME_PROOF",
        action_input={"monthly_income": 85000},
        manifest=pack,
        now=fixed_time,
    )

    for _ in range(100):
        t = deterministic_check(
            snapshot=snap,
            expected_snapshot_id=snap.snapshot_id,
            action_id="UPLOAD_INCOME_PROOF",
            action_input={"monthly_income": 85000},
            manifest=pack,
            now=fixed_time,
        )
        assert t.journey_id == first_token.journey_id
        assert t.action_id == first_token.action_id
        assert t.new_values == first_token.new_values
        assert t.direct_fields == first_token.direct_fields
        assert t.created_at == first_token.created_at
