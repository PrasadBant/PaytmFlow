import copy

import pytest

from app.packs.contract import JourneyPackManifest
from app.packs.validator import validate_manifest

VALID_BASELINE_MANIFEST_DICT = {
    "metadata": {
        "journey_type": "LENDING",
        "schema_version": "1.0.0",
        "display_name": "Personal Loan Offerings",
        "description": "Instant unsecured personal loan",
        "icon": "rupee",
        "flagship_demo": True,
        "lifecycle_status": "SUPPORTED",
        "supports_natural_language": True,
    },
    "goal_schema": [
        {
            "key": "loan_amount",
            "type": "money",
            "label": "Loan Amount (₹)",
            "required": True,
        }
    ],
    "state_schema": [
        {
            "key": "f_init",
            "label": "Initial KYC",
            "type": "boolean",
            "default_status": "SATISFIED",
        },
        {"key": "f_income", "label": "Income", "type": "money", "default_status": "BLOCKED"},
        {"key": "f_emp", "label": "Employment", "type": "text", "default_status": "BLOCKED"},
        {"key": "f_bureau", "label": "Bureau", "type": "boolean", "default_status": "BLOCKED"},
        {
            "key": "f_alt1",
            "label": "Alternate Option 1",
            "type": "text",
            "default_status": "BLOCKED",
        },
        {
            "key": "f_alt2",
            "label": "Alternate Option 2",
            "type": "text",
            "default_status": "BLOCKED",
        },
        {
            "key": "f_agreement",
            "label": "Agreement",
            "type": "boolean",
            "default_status": "BLOCKED",
        },
    ],
    "dependencies": [
        {"source": "f_init", "target": "f_income"},
        {"source": "f_income", "target": "f_emp"},
        {"source": "f_emp", "target": "f_bureau"},
        {"source": "f_bureau", "target": "f_agreement"},
    ],
    "actions": [
        {
            "action_id": "ACT_INCOME",
            "title": "Upload Income Proof",
            "kind": "EVIDENCE",
            "satisfies": ["f_income"],
            "preconditions": ["f_init"],
            # Integrity-hardening phase: `accepts` must list the doc_type
            # values evidence_mappings below actually routes here (the
            # real-manifest convention every one of the six journey
            # manifests follows) - an empty/missing `accepts` on an
            # EVIDENCE action with real evidence_mappings pointing at it
            # is exactly the class of defect
            # `validate_evidence_integrity`'s EVIDENCE_DOC_TYPE_NOT_ROUTABLE
            # check now catches, so a "valid baseline" fixture must not
            # have this gap either.
            "accepts": ["SALARY_SLIP", "BANK_STATEMENT", "ITR_V"],
        },
        {
            "action_id": "ACT_EMP",
            "title": "Declare Employment",
            "kind": "FORM",
            "satisfies": ["f_emp"],
            "preconditions": ["f_income"],
        },
        {
            "action_id": "ACT_BUREAU",
            "title": "Fetch Bureau Record",
            "kind": "FORM",
            "satisfies": ["f_bureau"],
            "preconditions": ["f_emp"],
        },
        {
            "action_id": "ACT_ALT1",
            "title": "Add Co-applicant",
            "kind": "FORM",
            "satisfies": ["f_alt1"],
            "preconditions": ["f_init"],
        },
        {
            "action_id": "ACT_ALT2",
            "title": "Add Collateral Security",
            "kind": "FORM",
            "satisfies": ["f_alt2"],
            "preconditions": ["f_init"],
        },
        {
            "action_id": "ACT_AGREE",
            "title": "Accept Agreement",
            "kind": "FORM",
            "satisfies": ["f_agreement"],
            "preconditions": ["f_bureau"],
        },
    ],
    "action_groups": {},
    "evidence_mappings": [
        {
            "doc_type": "SALARY_SLIP",
            "target_field": "f_income",
            "confidence_threshold": 0.85,
            "action_id": "ACT_INCOME",
        },
        {
            "doc_type": "BANK_STATEMENT",
            "target_field": "f_income",
            "confidence_threshold": 0.80,
            "action_id": "ACT_INCOME",
        },
        {
            "doc_type": "ITR_V",
            "target_field": "f_income",
            "confidence_threshold": 0.90,
            "action_id": "ACT_INCOME",
        },
    ],
    "ambiguity_rules": [
        {
            "ambiguity_id": "INCOME_MISMATCH",
            "field": "f_income",
            "reason": "Difference between slip and statement",
            "question": "Select verified income",
            "answer_type": "MONEY",
        },
        {
            "ambiguity_id": "EMP_NAME_MISMATCH",
            "field": "f_emp",
            "reason": "Name spelling difference",
            "question": "Confirm exact employer name",
            "answer_type": "TEXT",
        },
    ],
    "readiness_rules": {
        "mandatory_fields": [
            "f_init",
            "f_income",
            "f_emp",
            "f_bureau",
            "f_alt1",
            "f_alt2",
            "f_agreement",
        ]
    },
    "ui_labels": {"status_heading": "Application Status"},
    "prohibited_claims": [],
    "simulation_defaults": {
        "f_income": 80000,
        "f_emp": "Salaried",
        "f_bureau": True,
        "f_alt1": "None",
        "f_alt2": "None",
        "f_agreement": True,
    },
}


def test_valid_baseline_manifest():
    manifest = JourneyPackManifest.model_validate(VALID_BASELINE_MANIFEST_DICT)
    violations = validate_manifest(manifest)
    assert len(violations) == 0, f"Expected 0 violations on valid baseline, got: {violations}"


@pytest.mark.parametrize(
    "broken_type,error_code",
    [
        ("unknown_field_ref", "UNKNOWN_FIELD_REF"),
        ("cyclic_dependency", "CYCLIC_DEPENDENCY"),
        ("below_contract_floor", "BELOW_CONTRACT_FLOOR"),
        ("duplicate_satisfier", "DUPLICATE_SATISFIER"),
        ("inconsistent_group", "INCONSISTENT_GROUP"),
        ("unreachable_field", "UNREACHABLE_FIELD"),
        ("shallow_cascade", "SHALLOW_CASCADE"),
        ("trivial_ordering", "TRIVIAL_ORDERING"),
        ("unreachable_ambiguity", "UNREACHABLE_AMBIGUITY"),
        ("prohibited_claim", "PROHIBITED_CLAIM"),
    ],
)
def test_deliberately_broken_manifests(broken_type, error_code):
    data = copy.deepcopy(VALID_BASELINE_MANIFEST_DICT)

    if broken_type == "unknown_field_ref":
        data["dependencies"].append({"source": "non_existent_field", "target": "f_income"})
    elif broken_type == "cyclic_dependency":
        data["dependencies"].append({"source": "f_bureau", "target": "f_init"})
    elif broken_type == "below_contract_floor":
        data["state_schema"] = data["state_schema"][:3]
    elif broken_type == "duplicate_satisfier":
        data["actions"].append(
            {
                "action_id": "ACT_INCOME_DUPLICATE",
                "title": "Duplicate Income Action",
                "kind": "FORM",
                "satisfies": ["f_income"],
                "preconditions": ["f_init"],
            }
        )
    elif broken_type == "inconsistent_group":
        data["action_groups"] = {
            "GRP1": {
                "primary": "ACT_INCOME",
                "members": ["ACT_INCOME", "ACT_EMP"],
            }
        }
    elif broken_type == "unreachable_field":
        data["actions"] = [a for a in data["actions"] if "f_agreement" not in a["satisfies"]]
    elif broken_type == "shallow_cascade":
        data["dependencies"] = [
            {"source": "f_init", "target": "f_income"},
            {"source": "f_init", "target": "f_emp"},
            {"source": "f_init", "target": "f_bureau"},
            {"source": "f_init", "target": "f_agreement"},
        ]
    elif broken_type == "trivial_ordering":
        data["actions"] = [
            {
                "action_id": "A1",
                "title": "A1",
                "kind": "FORM",
                "satisfies": ["f_income"],
                "preconditions": ["f_init"],
            },
            {
                "action_id": "A2",
                "title": "A2",
                "kind": "FORM",
                "satisfies": ["f_emp"],
                "preconditions": ["f_income"],
            },
            {
                "action_id": "A3",
                "title": "A3",
                "kind": "FORM",
                "satisfies": ["f_bureau"],
                "preconditions": ["f_emp"],
            },
            {
                "action_id": "A4",
                "title": "A4",
                "kind": "FORM",
                "satisfies": ["f_alt1"],
                "preconditions": ["f_bureau"],
            },
            {
                "action_id": "A5",
                "title": "A5",
                "kind": "FORM",
                "satisfies": ["f_alt2"],
                "preconditions": ["f_alt1"],
            },
            {
                "action_id": "A6",
                "title": "A6",
                "kind": "FORM",
                "satisfies": ["f_agreement"],
                "preconditions": ["f_alt2"],
            },
        ]
        data["dependencies"] = [
            {"source": "f_init", "target": "f_income"},
            {"source": "f_income", "target": "f_emp"},
            {"source": "f_emp", "target": "f_bureau"},
            {"source": "f_bureau", "target": "f_alt1"},
            {"source": "f_alt1", "target": "f_alt2"},
            {"source": "f_alt2", "target": "f_agreement"},
        ]
        data["evidence_mappings"][0]["action_id"] = "A1"
        data["evidence_mappings"][1]["action_id"] = "A1"
        data["evidence_mappings"][2]["action_id"] = "A1"
    elif broken_type == "unreachable_ambiguity":
        data["ambiguity_rules"].append(
            {
                "ambiguity_id": "UNREACHABLE_AMB",
                "field": "f_agreement",
                "reason": "Cannot be reached if disconnected",
                "question": "Question",
                "answer_type": "TEXT",
            }
        )
        data["actions"] = [a for a in data["actions"] if "f_agreement" not in a["satisfies"]]
    elif broken_type == "prohibited_claim":
        data["ui_labels"]["status_heading"] = "Your loan has guaranteed approval"

    manifest = JourneyPackManifest.model_validate(data)
    violations = validate_manifest(manifest)
    violation_codes = [v.code for v in violations]
    assert error_code in violation_codes, f"Expected {error_code} in {violation_codes}"
