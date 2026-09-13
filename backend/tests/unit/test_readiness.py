from app.core.models import (
    CoreAmbiguity,
    CoreFieldState,
    CoreFieldStatus,
    CoreReadiness,
)
from app.core.readiness import evaluate_readiness
from app.packs.contract import (
    FieldType,
    GoalFieldSpec,
    JourneyPackManifest,
    ManifestMetadata,
    PackIcon,
    ReadinessRulesSpec,
    StateFieldSpec,
)
from app.schemas.enums import JourneyType


def make_test_manifest(dead_end_conditions=None) -> JourneyPackManifest:
    return JourneyPackManifest(
        metadata=ManifestMetadata(
            journey_type=JourneyType.LENDING,
            schema_version="1.0.0",
            display_name="Test Lending",
            description="Manifest for readiness testing",
            icon=PackIcon.RUPEE,
        ),
        goal_schema=[
            GoalFieldSpec(key="loan_amount", type=FieldType.NUMBER, required=True, label="Amount")
        ],
        state_schema=[
            StateFieldSpec(
                key="pan_validated",
                label="PAN",
                type=FieldType.TEXT,
                mandatory=True,
            ),
            StateFieldSpec(
                key="monthly_income",
                label="Income",
                type=FieldType.MONEY,
                mandatory=True,
            ),
            StateFieldSpec(
                key="co_applicant",
                label="Co-Applicant",
                type=FieldType.TEXT,
                mandatory=True,
            ),
        ],
        dependencies=[],
        actions=[],
        readiness_rules=ReadinessRulesSpec(
            mandatory_fields=["pan_validated", "monthly_income", "co_applicant"],
            dead_end_conditions=dead_end_conditions,
        ),
    )


def test_readiness_not_ready():
    manifest = make_test_manifest()
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.BLOCKED,
            value=None,
            mandatory=True,
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.BLOCKED,
            value=None,
            mandatory=True,
        ),
    }

    readiness = evaluate_readiness(manifest, field_states)
    assert readiness == CoreReadiness.NOT_READY
    assert isinstance(readiness, CoreReadiness)
    assert isinstance(readiness.value, str)


def test_readiness_ready_with_not_applicable():
    manifest = make_test_manifest()
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.SATISFIED,
            value=85000,
            mandatory=True,
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.NOT_APPLICABLE,
            value=None,
            mandatory=True,
        ),
    }

    readiness = evaluate_readiness(manifest, field_states)
    assert readiness == CoreReadiness.READY


def test_readiness_needs_review():
    manifest = make_test_manifest()
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.AMBIGUOUS,
            value=85000,
            mandatory=True,
            ambiguity=CoreAmbiguity(
                ambiguity_id="INCOME_MISMATCH",
                field="monthly_income",
                reason="Bank statement does not match salary slip",
                question="Select correct income",
                answer_type="MONEY",
            ),
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.SATISFIED,
            value="John Doe",
            mandatory=True,
        ),
    }

    readiness = evaluate_readiness(manifest, field_states)
    assert readiness == CoreReadiness.NEEDS_REVIEW


def test_readiness_dead_end_via_condition():
    dead_ends = [
        {"field": "monthly_income", "op": "lt", "value": 25000},
    ]
    manifest = make_test_manifest(dead_end_conditions=dead_ends)
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.SATISFIED,
            value=15000,  # below 25000 threshold -> DEAD_END
            mandatory=True,
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.SATISFIED,
            value="Jane",
            mandatory=True,
        ),
    }

    readiness = evaluate_readiness(manifest, field_states)
    assert readiness == CoreReadiness.DEAD_END


def test_readiness_no_numeric_scores():
    manifest = make_test_manifest()
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.SATISFIED,
            value=85000,
            mandatory=True,
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.SATISFIED,
            value="Jane",
            mandatory=True,
        ),
    }

    readiness = evaluate_readiness(manifest, field_states)
    assert readiness in [
        CoreReadiness.READY,
        CoreReadiness.NOT_READY,
        CoreReadiness.NEEDS_REVIEW,
        CoreReadiness.DEAD_END,
    ]
    assert not isinstance(readiness, (int, float))
    assert readiness.value in ["READY", "NOT_READY", "NEEDS_REVIEW", "DEAD_END"]


def test_readiness_determinism_100_runs():
    manifest = make_test_manifest()
    field_states = {
        "pan_validated": CoreFieldState(
            key="pan_validated",
            label="PAN",
            status=CoreFieldStatus.SATISFIED,
            value="ABCDE1234F",
            mandatory=True,
        ),
        "monthly_income": CoreFieldState(
            key="monthly_income",
            label="Income",
            status=CoreFieldStatus.BLOCKED,
            value=None,
            mandatory=True,
        ),
        "co_applicant": CoreFieldState(
            key="co_applicant",
            label="Co-Applicant",
            status=CoreFieldStatus.BLOCKED,
            value=None,
            mandatory=True,
        ),
    }

    first = evaluate_readiness(manifest, field_states)
    for _ in range(100):
        assert evaluate_readiness(manifest, field_states) == first
