import pytest

from app.core.dependencies import DependencyGraph
from app.packs.contract import JourneyPackManifest
from app.packs.registry import pack_registry
from app.packs.validator import validate_manifest
from app.schemas.enums import JourneyType


@pytest.fixture(autouse=True)
def load_packs():
    pack_registry.load_all()


@pytest.mark.parametrize(
    "journey_type",
    [
        JourneyType.LENDING,
        JourneyType.INSURANCE,
        JourneyType.CREDIT_CARD,
        JourneyType.KYC,
    ],
)
def test_manifest_loads_and_passes_validator(journey_type: JourneyType):
    manifest = pack_registry.get_pack(journey_type)
    assert manifest is not None, f"Manifest for {journey_type} failed to load from YAML"
    assert isinstance(manifest, JourneyPackManifest)

    # Validate against strict pack validator rules
    violations = validate_manifest(manifest)
    assert len(violations) == 0, (
        f"Manifest {journey_type} has {len(violations)} validation violation(s): "
        f"{[f'{v.code}: {v.message}' for v in violations]}"
    )


# ACCOUNT_OPENING and INVESTMENT are deliberately NOT in the clean list above:
# each has a real, disclosed `evidence_mappings.action_id`/`target_field`
# manifest defect (found by hand during their own phases, now also caught
# structurally by `validate_evidence_integrity`'s
# ACTION_TARGET_FIELD_MISMATCH/EVIDENCE_DOC_TYPE_NOT_ROUTABLE checks - see
# docs/docai_account_opening_report.md §8/§14 and
# docs/docai_investment_report.md §O) that the integrity-hardening phase's
# explicit instructions say NOT to silently fix (repointing the action_id
# would mean guessing which action the manifest author intended, since no
# EVIDENCE action for PAN_CARD_IMAGE/KRA_KYC_LETTER's real target field
# exists). This test exposes those EXACT known defects precisely, rather
# than either hiding them behind a passing "0 violations" assertion or
# silently dropping manifest-validator coverage for these two packs: if the
# violation set for either journey ever changes (a real fix, or a NEW
# unrelated defect), this test fails and must be looked at, not silently
# adjusted.
_KNOWN_ACCOUNT_OPENING_VIOLATIONS = {
    ("ACTION_TARGET_FIELD_MISMATCH", "PAN_CARD_IMAGE"),
    ("EVIDENCE_DOC_TYPE_NOT_ROUTABLE", "PAN_CARD_IMAGE"),
    # AADHAAR_FRONT_BACK / upload_digital_signature's `accepts` (was
    # ["image/png"]) was FIXED in the manifest-integrity + confidence-
    # calibration phase - confirmed unambiguous by the frozen contract
    # ("Allowed doc_type values for EVIDENCE actions", no exception) AND
    # the frontend (Screen06UploadEvidence.tsx reads `accepts[0]` directly
    # as the doc_type to submit). Only PAN_CARD_IMAGE's defect remains,
    # since no EVIDENCE action exists that correctly satisfies
    # `pan_authenticated` to repoint it to.
}
_KNOWN_INVESTMENT_VIOLATIONS = {
    ("ACTION_TARGET_FIELD_MISMATCH", "KRA_KYC_LETTER"),
    ("EVIDENCE_DOC_TYPE_NOT_ROUTABLE", "KRA_KYC_LETTER"),
}


@pytest.mark.parametrize(
    ("journey_type", "expected_violations"),
    [
        (JourneyType.ACCOUNT_OPENING, _KNOWN_ACCOUNT_OPENING_VIOLATIONS),
        (JourneyType.INVESTMENT, _KNOWN_INVESTMENT_VIOLATIONS),
    ],
)
def test_known_manifest_defects_are_exposed_not_hidden(journey_type, expected_violations):
    manifest = pack_registry.get_pack(journey_type)
    assert manifest is not None

    violations = validate_manifest(manifest)
    actual = {(v.code, v.field_or_id) for v in violations}
    assert actual == expected_violations, (
        f"{journey_type}'s manifest-validator violations changed - expected exactly "
        f"{expected_violations}, got {actual}. If this is a genuine fix, update this "
        f"test's expectation explicitly (not by weakening it); if it's a NEW, "
        f"different defect, investigate before assuming it's safe."
    )


@pytest.mark.parametrize(
    "journey_type",
    [
        JourneyType.LENDING,
        JourneyType.INSURANCE,
        JourneyType.CREDIT_CARD,
        JourneyType.KYC,
        JourneyType.ACCOUNT_OPENING,
        JourneyType.INVESTMENT,
    ],
)
def test_manifest_contract_depth_quality(journey_type: JourneyType):
    manifest = pack_registry.get_pack(journey_type)
    assert manifest is not None

    # 1. State schema depth (>= 6 fields)
    assert len(manifest.state_schema) >= 6, (
        f"{journey_type} must have at least 6 state fields, got {len(manifest.state_schema)}"
    )

    # 2. Non-empty goal schema with labels and types
    assert len(manifest.goal_schema) >= 1
    for gf in manifest.goal_schema:
        assert gf.key and gf.label and gf.type

    # 3. Actions coverage (>= 5 actions)
    assert len(manifest.actions) >= 5, (
        f"{journey_type} must have at least 5 actions, got {len(manifest.actions)}"
    )

    # 4. Evidence mappings (>= 2 mappings)
    assert len(manifest.evidence_mappings) >= 2, (
        f"{journey_type} must have >= 2 evidence mappings, got {len(manifest.evidence_mappings)}"
    )

    # 5. Ambiguity rules (>= 2 reachable ambiguity rules)
    assert len(manifest.ambiguity_rules or []) >= 2, (
        f"{journey_type} must have >= 2 ambiguity rules, got {len(manifest.ambiguity_rules or [])}"
    )

    # 6. Dependency DAG (at least 4 edges)
    assert len(manifest.dependencies) >= 4, (
        f"{journey_type} must have at least 4 dependency edges, got {len(manifest.dependencies)}"
    )

    # 7. Simulation defaults must provide values for all non-satisfied mandatory fields
    satisfied_by_default = {f.key for f in manifest.state_schema if f.default_status == "SATISFIED"}
    for f in manifest.state_schema:
        if f.mandatory and not f.derived and f.key not in satisfied_by_default:
            assert f.key in manifest.simulation_defaults, (
                f"{journey_type} simulation_defaults missing key '{f.key}'"
            )


def test_account_opening_dag_structure():
    manifest = pack_registry.get_pack(JourneyType.ACCOUNT_OPENING)
    assert manifest is not None

    # Linear and nominee branches meeting at vkyc_completed
    graph = DependencyGraph(manifest)
    prereqs = graph.get_direct_prerequisites("vkyc_completed")
    assert "nominee_declared" in prereqs
    assert "signature_uploaded" in prereqs
    assert "nominee_satisfaction" in manifest.action_groups
    assert manifest.action_groups["nominee_satisfaction"].primary == "declare_account_nominee"


def test_investment_dag_structure():
    manifest = pack_registry.get_pack(JourneyType.INVESTMENT)
    assert manifest is not None

    # Two converging chains meeting at nomination_and_fatca_signed
    graph = DependencyGraph(manifest)
    prereqs = graph.get_direct_prerequisites("nomination_and_fatca_signed")
    assert "risk_assessment_completed" in prereqs
    assert "sip_mandate_approved" in prereqs
    assert "bank_verification_satisfaction" in manifest.action_groups
    assert (
        manifest.action_groups["bank_verification_satisfaction"].primary
        == "upload_cancelled_cheque"
    )


def test_insurance_dag_structure():
    manifest = pack_registry.get_pack(JourneyType.INSURANCE)
    assert manifest is not None

    # Underwriting and mandate branches meeting at policy_terms_accepted
    graph = DependencyGraph(manifest)
    prereqs = graph.get_direct_prerequisites("policy_terms_accepted")
    assert "tele_underwriting_scheduled" in prereqs
    assert "bank_mandate_registered" in prereqs
    assert "ped_satisfaction" in manifest.action_groups
    assert manifest.action_groups["ped_satisfaction"].primary == "submit_ped_records"


def test_credit_card_dag_structure():
    manifest = pack_registry.get_pack(JourneyType.CREDIT_CARD)
    assert manifest is not None

    # Income, employment and address branches converging at card_agreement_signed
    graph = DependencyGraph(manifest)
    prereqs = graph.get_direct_prerequisites("card_agreement_signed")
    assert "income_verified" in prereqs
    assert "employment_verified" in prereqs
    assert "delivery_address_confirmed" in prereqs
    assert "income_proof_satisfaction" in manifest.action_groups
    assert manifest.action_groups["income_proof_satisfaction"].primary == "upload_salary_statement"


def test_kyc_dag_structure():
    manifest = pack_registry.get_pack(JourneyType.KYC)
    assert manifest is not None

    # PAN, OVD and Geolocation converging at rekyc_declaration_signed
    graph = DependencyGraph(manifest)
    prereqs = graph.get_direct_prerequisites("rekyc_declaration_signed")
    assert "pan_linked" in prereqs
    assert "ovd_document_uploaded" in prereqs
    assert "geo_tag_validated" in prereqs
    assert "ovd_satisfaction" in manifest.action_groups
    assert manifest.action_groups["ovd_satisfaction"].primary == "upload_passport_ovd"
