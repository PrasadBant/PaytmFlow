from uuid import uuid4

from app.core.models import (
    CoreFieldState,
    CoreFieldStatus,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.planner import (
    NoPath,
    PlanResult,
    plan,
)
from app.core.rules import derive_field_states
from app.packs.contract import (
    ActionGroupSpec,
    ActionKind,
    ActionSpec,
    DependencyEdge,
    FieldType,
    GoalFieldSpec,
    JourneyPackManifest,
    ManifestMetadata,
    PackIcon,
    ReadinessRulesSpec,
    StateFieldSpec,
)
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


def test_planner_100_runs_determinism():
    snapshot, pack = get_lending_initial_snapshot()

    first_result = plan(snapshot, pack)
    assert isinstance(first_result, PlanResult)
    assert first_result.is_path_found is True
    assert len(first_result.actions) > 0

    first_action_ids = [a.action_id for a in first_result.actions]
    first_unblock_counts = [a.transitive_unblock_count for a in first_result.actions]

    for _ in range(100):
        res = plan(snapshot, pack)
        assert res.is_path_found is True
        assert [a.action_id for a in res.actions] == first_action_ids
        assert [a.transitive_unblock_count for a in res.actions] == first_unblock_counts
        assert res.minimum_path_length == first_result.minimum_path_length


def test_planner_multi_blocker_ordering():
    snapshot, pack = get_lending_initial_snapshot()

    result = plan(snapshot, pack)
    assert result.is_path_found is True
    action_ids = [a.action_id for a in result.actions]

    # In Lending initial state, SUBMIT_EMPLOYMENT_INFO unblocks employer_name and
    # loan_offer_accepted (count=2), UPLOAD_INCOME_PROOF unblocks loan_offer_accepted (count=1),
    # ACCEPT_LOAN_TERMS unblocks 0.
    assert "SUBMIT_EMPLOYMENT_INFO" in action_ids
    assert "UPLOAD_INCOME_PROOF" in action_ids
    assert "ACCEPT_LOAN_TERMS" in action_ids

    emp_idx = action_ids.index("SUBMIT_EMPLOYMENT_INFO")
    accept_idx = action_ids.index("ACCEPT_LOAN_TERMS")
    assert emp_idx < accept_idx

    emp_action = next(a for a in result.actions if a.action_id == "SUBMIT_EMPLOYMENT_INFO")
    accept_action = next(a for a in result.actions if a.action_id == "ACCEPT_LOAN_TERMS")
    assert emp_action.transitive_unblock_count > accept_action.transitive_unblock_count


def test_planner_all_fields_satisfied_returns_empty_plan():
    snapshot, pack = get_lending_initial_snapshot()
    all_satisfied_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
        "monthly_income": 85000,
        "employment_type": "SALARIED",
        "employer_name": "Acme Inc",
        "loan_offer_accepted": True,
    }
    states, _ = derive_field_states(pack, all_satisfied_values)

    ready_snapshot = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=snapshot.journey_id,
        journey_type="LENDING",
        version_number=5,
        readiness=CoreReadiness.READY,
        fields=states,
        goal=snapshot.goal,
    )

    result = plan(ready_snapshot, pack)
    assert result.is_path_found is True
    assert len(result.actions) == 0
    assert result.minimum_path_length == 0


def test_planner_unreachable_mandatory_field_returns_no_path():
    # Construct a manifest where a mandatory non-derived field has no satisfying action
    broken_manifest = JourneyPackManifest(
        metadata=ManifestMetadata(
            journey_type=JourneyType.LENDING,
            schema_version="1.0.0",
            display_name="Broken Pack",
            description="Manifest with missing action for mandatory field",
            icon=PackIcon.RUPEE,
        ),
        goal_schema=[
            GoalFieldSpec(
                key="amount",
                type=FieldType.NUMBER,
                required=True,
                label="Amount",
            )
        ],
        state_schema=[
            StateFieldSpec(key="field_a", label="Field A", type=FieldType.TEXT, mandatory=True),
            # field_b has no satisfying action!
            StateFieldSpec(key="field_b", label="Field B", type=FieldType.TEXT, mandatory=True),
        ],
        dependencies=[
            DependencyEdge(
                source="field_a",
                target="field_b",
            )
        ],
        actions=[
            ActionSpec(
                action_id="ACTION_A",
                title="Do A",
                kind=ActionKind.FORM,
                satisfies=["field_a"],
                preconditions=[],
                why="Fills field_a",
            )
        ],
        readiness_rules=ReadinessRulesSpec(mandatory_fields=["field_a", "field_b"]),
    )

    snapshot = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="LENDING",
        version_number=1,
        goal={"amount": 1000},
        fields={
            "field_a": CoreFieldState(
                key="field_a",
                label="Field A",
                status=CoreFieldStatus.BLOCKED,
                mandatory=True,
            ),
            "field_b": CoreFieldState(
                key="field_b",
                label="Field B",
                status=CoreFieldStatus.BLOCKED,
                mandatory=True,
            ),
        },
        readiness=CoreReadiness.NOT_READY,
    )

    result = plan(snapshot, broken_manifest)
    assert isinstance(result, NoPath)
    assert result.is_path_found is False
    assert "field_b" in (result.reason or "")


def test_planner_action_group_resolution():
    # If two actions satisfy the same field under an action_group, planner picks primary
    group_manifest = JourneyPackManifest(
        metadata=ManifestMetadata(
            journey_type=JourneyType.KYC,
            schema_version="1.0.0",
            display_name="Group Pack",
            description="Manifest with action groups",
            icon=PackIcon.SHIELD,
        ),
        goal_schema=[],
        state_schema=[
            StateFieldSpec(
                key="identity_verified",
                label="Identity",
                type=FieldType.BOOLEAN,
                mandatory=True,
            ),
        ],
        dependencies=[],
        action_groups={
            "IDENTITY_VERIFY_GROUP": ActionGroupSpec(
                primary="VERIFY_VIA_DIGILOCKER",
                members=["VERIFY_VIA_DIGILOCKER", "UPLOAD_PASSPORT_MANUAL"],
            )
        },
        actions=[
            ActionSpec(
                action_id="VERIFY_VIA_DIGILOCKER",
                title="Verify DigiLocker",
                kind=ActionKind.FORM,
                satisfies=["identity_verified"],
                preconditions=[],
                action_group="IDENTITY_VERIFY_GROUP",
                why="Primary verification",
            ),
            ActionSpec(
                action_id="UPLOAD_PASSPORT_MANUAL",
                title="Upload Passport",
                kind=ActionKind.EVIDENCE,
                satisfies=["identity_verified"],
                preconditions=[],
                action_group="IDENTITY_VERIFY_GROUP",
                why="Alternative verification",
            ),
        ],
        readiness_rules=ReadinessRulesSpec(mandatory_fields=["identity_verified"]),
    )

    snapshot = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="KYC",
        version_number=1,
        goal={},
        fields={
            "identity_verified": CoreFieldState(
                key="identity_verified",
                label="Identity",
                status=CoreFieldStatus.BLOCKED,
                mandatory=True,
            ),
        },
        readiness=CoreReadiness.NOT_READY,
    )

    result = plan(snapshot, group_manifest)
    assert result.is_path_found is True
    assert len(result.actions) == 1
    assert result.actions[0].action_id == "VERIFY_VIA_DIGILOCKER"


def test_planner_excludes_not_applicable_fields():
    # A conditional field that evaluates to NOT_APPLICABLE is not planned for
    cond_manifest = JourneyPackManifest(
        metadata=ManifestMetadata(
            journey_type=JourneyType.INSURANCE,
            schema_version="1.0.0",
            display_name="Conditional Pack",
            description="Manifest with conditional field",
            icon=PackIcon.SHIELD,
        ),
        goal_schema=[
            GoalFieldSpec(
                key="has_co_applicant",
                type=FieldType.BOOLEAN,
                required=True,
                label="Has Co-Applicant",
            )
        ],
        state_schema=[
            StateFieldSpec(
                key="applicant_name",
                label="Applicant",
                type=FieldType.TEXT,
                mandatory=True,
            ),
            StateFieldSpec(
                key="co_applicant_name",
                label="Co-Applicant",
                type=FieldType.TEXT,
                mandatory=True,
            ),
        ],
        dependencies=[
            DependencyEdge(
                source="applicant_name",
                target="co_applicant_name",
                condition={"has_co_applicant": True},
            )
        ],
        actions=[
            ActionSpec(
                action_id="ENTER_APPLICANT",
                title="Enter Applicant",
                kind=ActionKind.FORM,
                satisfies=["applicant_name"],
                preconditions=[],
                why="Applicant info",
            ),
            ActionSpec(
                action_id="ENTER_CO_APPLICANT",
                title="Enter Co-Applicant",
                kind=ActionKind.FORM,
                satisfies=["co_applicant_name"],
                preconditions=[],
                why="Co-Applicant info",
            ),
        ],
        readiness_rules=ReadinessRulesSpec(
            mandatory_fields=["applicant_name", "co_applicant_name"]
        ),
    )

    # When co_applicant_name is marked NOT_APPLICABLE in snapshot
    snapshot = CoreSnapshot(
        snapshot_id=uuid4(),
        journey_id=uuid4(),
        journey_type="INSURANCE",
        version_number=1,
        goal={"has_co_applicant": False},
        fields={
            "applicant_name": CoreFieldState(
                key="applicant_name",
                label="Applicant",
                status=CoreFieldStatus.BLOCKED,
                mandatory=True,
            ),
            "co_applicant_name": CoreFieldState(
                key="co_applicant_name",
                label="Co-Applicant",
                status=CoreFieldStatus.NOT_APPLICABLE,
                mandatory=True,
            ),
        },
        readiness=CoreReadiness.NOT_READY,
    )

    result = plan(snapshot, cond_manifest)
    assert result.is_path_found is True
    assert len(result.actions) == 1
    assert result.actions[0].action_id == "ENTER_APPLICANT"
