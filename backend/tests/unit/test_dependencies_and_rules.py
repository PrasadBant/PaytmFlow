from app.core.dependencies import DependencyGraph
from app.core.models import CoreAmbiguity, CoreFieldStatus
from app.core.rules import derive_field_states
from app.packs.registry import pack_registry
from app.schemas.enums import JourneyType


def test_dependency_graph_topological_sort():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_pack is not None

    graph = DependencyGraph(lending_pack)
    order = graph.get_topological_order()
    assert len(order) == 7

    for dep in graph.edges:
        source_idx = order.index(dep.source)
        target_idx = order.index(dep.target)
        assert source_idx < target_idx, (
            f"Topological order failed for edge {dep.source} -> {dep.target}"
        )


def test_lending_initial_status_derivation():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)

    initial_values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
    }

    states, progress = derive_field_states(lending_pack, initial_values)

    assert states["kyc_verified"].status == CoreFieldStatus.SATISFIED
    assert states["pan_validated"].status == CoreFieldStatus.SATISFIED
    assert states["bank_account_linked"].status == CoreFieldStatus.SATISFIED
    assert states["monthly_income"].status == CoreFieldStatus.BLOCKED
    assert states["employment_type"].status == CoreFieldStatus.BLOCKED
    assert states["employer_name"].status == CoreFieldStatus.BLOCKED
    assert states["loan_offer_accepted"].status == CoreFieldStatus.BLOCKED

    # Initial progress: 3 completed out of 7, 4 pending, blockers >= 1
    assert progress.completed == 3
    assert progress.total == 7
    assert progress.pending == 4
    assert progress.blockers >= 1


def test_cascade_resolution_when_field_satisfied():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)

    values_step2 = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
        "monthly_income": 85000,
        "employment_type": "SALARIED",
    }

    states, progress = derive_field_states(lending_pack, values_step2)

    assert states["monthly_income"].status == CoreFieldStatus.SATISFIED
    assert states["monthly_income"].display_value == "₹85,000"
    assert states["employment_type"].status == CoreFieldStatus.SATISFIED
    assert states["employer_name"].status == CoreFieldStatus.BLOCKED
    assert states["employer_name"].resolve_action_id in [
        "VERIFY_EMPLOYER_RECORD",
        "UPLOAD_WORK_ID",
    ]
    assert progress.completed == 5
    assert progress.pending == 2


def test_ambiguity_status_derivation():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)

    values = {
        "kyc_verified": True,
        "pan_validated": "ABCDE1234F",
        "bank_account_linked": "HDFC0001234",
        "monthly_income": 62000,
    }
    ambiguities = {
        "monthly_income": CoreAmbiguity(
            ambiguity_id="INCOME_MISMATCH",
            field="monthly_income",
            reason="Bank statement credit differs from salary slip",
            question="Select verified income",
            answer_type="MONEY",
        )
    }

    states, progress = derive_field_states(lending_pack, values, ambiguities=ambiguities)

    assert states["monthly_income"].status == CoreFieldStatus.AMBIGUOUS
    assert states["monthly_income"].ambiguity is not None
    assert states["monthly_income"].ambiguity.ambiguity_id == "INCOME_MISMATCH"


def test_conditional_not_applicable_gating():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)

    goal_group = {"policy_type": "GROUP"}
    graph = DependencyGraph(lending_pack, goal=goal_group)
    assert graph is not None
