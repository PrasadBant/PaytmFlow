from uuid import uuid4

from app.core.diff import compute_diff
from app.core.models import (
    CoreAmbiguity,
    CoreFieldState,
    CoreFieldStatus,
    CoreJourneyDiff,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.rules import derive_field_states
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType


def get_lending_snapshots():
    pack_registry.load_all()
    pack = pack_registry.get_pack(JourneyType.LENDING)
    assert pack is not None

    # Snapshot v1: 3/7 satisfied
    v1_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
    }
    v1_states, _ = derive_field_states(pack, v1_values)
    snap_v1 = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields=v1_states,
        goal={"loan_amount": 200000, "tenure_months": 24},
    )

    # Snapshot v2: 4/7 satisfied (monthly_income added)
    v2_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
        "monthly_income": 85000,
    }
    v2_states, _ = derive_field_states(pack, v2_values)
    snap_v2 = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=snap_v1.journey_id,
        journey_type="LENDING",
        version_number=2,
        readiness=CoreReadiness.NOT_READY,
        fields=v2_states,
        goal=snap_v1.goal,
    )

    return snap_v1, snap_v2, pack


def test_compute_diff_lending_v1_to_v2():
    snap_v1, snap_v2, pack = get_lending_snapshots()

    diff = compute_diff(
        snapshot_a=snap_v1,
        snapshot_b=snap_v2,
        manifest=pack,
        direct_fields={"monthly_income"},
        cause="ACTION:UPLOAD_INCOME_PROOF",
    )

    assert isinstance(diff, CoreJourneyDiff)
    assert diff.from_version == 1
    assert diff.to_version == 2

    # fields_changed
    assert len(diff.fields_changed) == 1
    fc = diff.fields_changed[0]
    assert fc.key == "monthly_income"
    assert fc.from_status == CoreFieldStatus.BLOCKED
    assert fc.to_status == CoreFieldStatus.SATISFIED
    assert fc.display_value == "₹85,000"
    assert fc.cause == "ACTION:UPLOAD_INCOME_PROOF"
    assert fc.cascaded is False

    # progress
    assert diff.progress is not None
    assert diff.progress.from_progress.completed == 3
    assert diff.progress.to_progress.completed == 4

    # actions
    assert "UPLOAD_INCOME_PROOF" in diff.actions_removed


def test_compute_diff_cascaded_vs_direct():
    snap_v1, _, pack = get_lending_snapshots()

    # Create a v3 where both employment_type (direct) and employer_name (cascaded/direct) change
    v3_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
        "employment_type": "SALARIED",
        "employer_name": "Acme Inc",
    }
    v3_states, _ = derive_field_states(pack, v3_values)
    snap_v3 = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=snap_v1.journey_id,
        journey_type="LENDING",
        version_number=3,
        readiness=CoreReadiness.NOT_READY,
        fields=v3_states,
        goal=snap_v1.goal,
    )

    diff = compute_diff(
        snapshot_a=snap_v1,
        snapshot_b=snap_v3,
        manifest=pack,
        direct_fields={"employment_type"},  # Only employment_type is direct
        cause="ACTION:SUBMIT_EMPLOYMENT_INFO",
    )

    emp_change = next(c for c in diff.fields_changed if c.key == "employment_type")
    assert emp_change.cascaded is False

    employer_change = next(c for c in diff.fields_changed if c.key == "employer_name")
    assert employer_change.cascaded is True


def test_compute_diff_empty_diff():
    snap_v1, _, pack = get_lending_snapshots()

    diff = compute_diff(
        snapshot_a=snap_v1,
        snapshot_b=snap_v1,
        manifest=pack,
    )

    assert diff.from_version == 1
    assert diff.to_version == 1
    assert len(diff.fields_changed) == 0
    assert len(diff.actions_unlocked) == 0
    assert len(diff.actions_removed) == 0
    assert diff.readiness.from_readiness == diff.readiness.to_readiness
    assert diff.progress.from_progress == diff.progress.to_progress


def test_compute_diff_clarification_needs_review():
    snap_v1, _, pack = get_lending_snapshots()

    # Create a snapshot with an ambiguity
    ambiguity_states = dict(snap_v1.fields)
    ambiguity_states["monthly_income"] = CoreFieldState(
        key="monthly_income",
        label="Monthly Net Income",
        status=CoreFieldStatus.AMBIGUOUS,
        value=62000,
        display_value="₹62,000",
        mandatory=True,
        ambiguity=CoreAmbiguity(
            ambiguity_id="INCOME_MISMATCH",
            field="monthly_income",
            reason="Bank statement does not match salary slip",
            question="Which income is correct?",
            answer_type="MONEY",
        ),
    )
    snap_ambiguous = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=snap_v1.journey_id,
        journey_type="LENDING",
        version_number=3,
        readiness=CoreReadiness.NEEDS_REVIEW,
        fields=ambiguity_states,
        goal=snap_v1.goal,
    )

    # Resolved snapshot
    resolved_states = dict(snap_v1.fields)
    resolved_states["monthly_income"] = CoreFieldState(
        key="monthly_income",
        label="Monthly Net Income",
        status=CoreFieldStatus.SATISFIED,
        value=85000,
        display_value="₹85,000",
        mandatory=True,
    )
    snap_resolved = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=snap_v1.journey_id,
        journey_type="LENDING",
        version_number=4,
        readiness=CoreReadiness.NOT_READY,
        fields=resolved_states,
        goal=snap_v1.goal,
    )

    diff = compute_diff(
        snapshot_a=snap_ambiguous,
        snapshot_b=snap_resolved,
        manifest=pack,
        direct_fields={"monthly_income"},
        cause="CLARIFICATION:INCOME_MISMATCH",
    )

    assert len(diff.fields_changed) == 1
    fc = diff.fields_changed[0]
    assert fc.key == "monthly_income"
    assert fc.from_status == CoreFieldStatus.AMBIGUOUS
    assert fc.to_status == CoreFieldStatus.SATISFIED
    assert diff.readiness.from_readiness == CoreReadiness.NEEDS_REVIEW
    assert diff.readiness.to_readiness == CoreReadiness.NOT_READY


def test_compute_diff_purity_100_runs():
    snap_v1, snap_v2, pack = get_lending_snapshots()

    first_diff = compute_diff(
        snapshot_a=snap_v1,
        snapshot_b=snap_v2,
        manifest=pack,
        direct_fields={"monthly_income"},
        cause="ACTION:UPLOAD_INCOME_PROOF",
    )

    for _ in range(100):
        diff = compute_diff(
            snapshot_a=snap_v1,
            snapshot_b=snap_v2,
            manifest=pack,
            direct_fields={"monthly_income"},
            cause="ACTION:UPLOAD_INCOME_PROOF",
        )
        assert diff == first_diff
