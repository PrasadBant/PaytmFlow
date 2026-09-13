from app.packs.contract import (
    ActionKind,
    FieldStatus,
    FieldType,
    JourneyPackManifest,
    JourneyType,
    PackIcon,
)


def test_minimal_manifest_parsing():
    raw_data = {
        "metadata": {
            "journey_type": "LENDING",
            "schema_version": "1.0.0",
            "display_name": "Personal Loan",
            "description": "Quick personal loan",
            "icon": "rupee",
            "flagship_demo": True,
            "lifecycle_status": "SUPPORTED",
            "supports_natural_language": True,
        },
        "goal_schema": [
            {
                "key": "amount",
                "type": "money",
                "label": "Loan Amount",
                "required": True,
                "min": 50000,
                "max": 500000,
            }
        ],
        "state_schema": [
            {
                "key": "income_verified",
                "label": "Income Verification",
                "type": "boolean",
                "mandatory": True,
                "derived": False,
                "display": True,
                "default_status": "BLOCKED",
            }
        ],
        "dependencies": [],
        "actions": [
            {
                "action_id": "UPLOAD_INCOME_PROOF",
                "title": "Upload Salary Slip",
                "kind": "EVIDENCE",
                "satisfies": ["income_verified"],
                "preconditions": [],
            }
        ],
        "evidence_mappings": [],
        "ambiguity_rules": [],
        "readiness_rules": {"mandatory_fields": ["income_verified"]},
        "ui_labels": {"goal_heading": "Customize Loan"},
        "prohibited_claims": ["guaranteed approval", "100% approval"],
        "simulation_defaults": {"income_verified": True},
    }

    manifest = JourneyPackManifest.model_validate(raw_data)
    assert manifest.metadata.journey_type == JourneyType.LENDING
    assert manifest.metadata.icon == PackIcon.RUPEE
    assert manifest.metadata.flagship_demo is True
    assert len(manifest.goal_schema) == 1
    assert manifest.goal_schema[0].type == FieldType.MONEY
    assert len(manifest.state_schema) == 1
    assert manifest.state_schema[0].default_status == FieldStatus.BLOCKED
    assert len(manifest.actions) == 1
    assert manifest.actions[0].kind == ActionKind.EVIDENCE
    assert manifest.readiness_rules.mandatory_fields == ["income_verified"]
    assert "guaranteed approval" in manifest.prohibited_claims


def test_full_manifest_with_groups_and_ambiguity():
    raw_data = {
        "metadata": {
            "journey_type": "INVESTMENT",
            "schema_version": "1.0.0",
            "display_name": "Mutual Funds",
            "description": "Invest in mutual funds",
            "icon": "chart",
            "flagship_demo": False,
            "lifecycle_status": "SUPPORTED",
            "supports_natural_language": False,
        },
        "goal_schema": [
            {
                "key": "sip_amount",
                "type": "money",
                "label": "Monthly SIP",
                "required": True,
            }
        ],
        "state_schema": [
            {
                "key": "pan_verified",
                "label": "Investor PAN",
                "type": "text",
                "mandatory": True,
            },
            {
                "key": "kra_kyc_status",
                "label": "KRA KYC Record",
                "type": "boolean",
                "mandatory": True,
            },
        ],
        "dependencies": [
            {
                "source": "pan_verified",
                "target": "kra_kyc_status",
            }
        ],
        "actions": [
            {
                "action_id": "VERIFY_PAN",
                "title": "Verify PAN",
                "kind": "FORM",
                "satisfies": ["pan_verified"],
            },
            {
                "action_id": "VERIFY_INVESTOR_IDENTITY",
                "title": "Fetch KRA via PAN",
                "kind": "FORM",
                "satisfies": ["kra_kyc_status"],
                "preconditions": ["pan_verified"],
                "action_group": "KRA_VERIFICATION_GROUP",
            },
            {
                "action_id": "LINK_KYC_RESULT",
                "title": "Link Aadhaar KYC",
                "kind": "FORM",
                "satisfies": ["kra_kyc_status"],
                "preconditions": ["pan_verified"],
                "action_group": "KRA_VERIFICATION_GROUP",
            },
        ],
        "action_groups": {
            "KRA_VERIFICATION_GROUP": {
                "primary": "VERIFY_INVESTOR_IDENTITY",
                "members": ["VERIFY_INVESTOR_IDENTITY", "LINK_KYC_RESULT"],
            }
        },
        "evidence_mappings": [
            {
                "doc_type": "PAN_CARD",
                "target_field": "pan_verified",
                "confidence_threshold": 0.85,
                "action_id": "VERIFY_PAN",
            }
        ],
        "ambiguity_rules": [
            {
                "ambiguity_id": "PAN_NAME_MISMATCH",
                "field": "pan_verified",
                "reason": "Name on PAN differs from application name",
                "question": "Which name should be registered on your portfolio?",
                "answer_type": "CHOICE",
                "choices": [
                    {"value": "APP_NAME", "label": "Use application name"},
                    {"value": "PAN_NAME", "label": "Use PAN name"},
                ],
            }
        ],
        "readiness_rules": {"mandatory_fields": ["pan_verified", "kra_kyc_status"]},
        "ui_labels": {},
        "prohibited_claims": [],
        "simulation_defaults": {
            "pan_verified": "ABCDE1234F",
            "kra_kyc_status": True,
        },
    }

    manifest = JourneyPackManifest.model_validate(raw_data)
    assert manifest.metadata.journey_type == JourneyType.INVESTMENT
    assert manifest.action_groups is not None
    assert "KRA_VERIFICATION_GROUP" in manifest.action_groups
    assert manifest.action_groups["KRA_VERIFICATION_GROUP"].primary == "VERIFY_INVESTOR_IDENTITY"
    assert len(manifest.ambiguity_rules) == 1
    assert manifest.ambiguity_rules[0].ambiguity_id == "PAN_NAME_MISMATCH"
