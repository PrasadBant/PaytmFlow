from uuid import uuid4

from app.core.models import CoreReadiness, CoreSnapshot
from app.core.rules import derive_field_states
from app.core.simulate import simulate
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType


def get_lending_initial_snapshot():
    pack_registry.load_all()
    pack = pack_registry.get_pack(JourneyType.LENDING)
    assert pack is not None

    initial_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
    }
    states, _ = derive_field_states(pack, initial_values)

    return CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="LENDING",
        version_number=1,
        readiness=CoreReadiness.NOT_READY,
        fields=states,
        goal={"loan_amount": 200000, "loan_purpose": "HOME_RENOVATION", "tenure_months": 24},
    ), pack


def test_simulate_income_proof_action():
    snapshot, pack = get_lending_initial_snapshot()

    result = simulate(
        action_id="UPLOAD_INCOME_PROOF",
        action_input={"monthly_income": 85000},
        snapshot=snapshot,
        manifest=pack,
    )

    # Assert newly satisfied fields
    satisfied_keys = [item.key for item in result.newly_satisfied]
    assert "monthly_income" in satisfied_keys

    # Assert progress transition 3/7 -> 4/7
    assert result.progress_before.completed == 3
    assert result.progress_after.completed == 4

    # Assert newly unlocked action
    unlocked_ids = [item.action_id for item in result.newly_unlocked]
    # SUBMIT_EMPLOYMENT_INFO or related actions
    assert "ACCEPT_LOAN_TERMS" not in unlocked_ids  # still blocked by employer_name

    # Still blocked fields
    blocked_keys = [item.key for item in result.still_blocked]
    assert "employment_type" in blocked_keys
    assert "employer_name" in blocked_keys
    assert "loan_offer_accepted" in blocked_keys


def test_simulate_purity_100_runs():
    snapshot, pack = get_lending_initial_snapshot()

    first_result = simulate(
        action_id="UPLOAD_INCOME_PROOF",
        action_input={"monthly_income": 85000},
        snapshot=snapshot,
        manifest=pack,
    )

    for _ in range(100):
        run_result = simulate(
            action_id="UPLOAD_INCOME_PROOF",
            action_input={"monthly_income": 85000},
            snapshot=snapshot,
            manifest=pack,
        )
        assert run_result == first_result
