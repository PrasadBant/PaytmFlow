from app.packs.registry import pack_registry
from app.packs.validator import validate_manifest
from app.schemas.enums import JourneyType


def test_lending_manifest_loads_and_validates():
    pack_registry.load_all()
    lending_pack = pack_registry.get_pack(JourneyType.LENDING)
    assert lending_pack is not None, "Lending manifest failed to load from lending.yaml"

    # Contract depth requirements
    assert len(lending_pack.state_schema) == 7, "Lending must have exactly 7 fields"
    assert len(lending_pack.dependencies) >= 4, "Lending must have at least 4 dependency edges"
    assert len(lending_pack.actions) == 6, "Lending must have 6 actions"
    assert len(lending_pack.evidence_mappings) == 4, "Lending must have 4 evidence mappings"
    assert len(lending_pack.ambiguity_rules) == 2, "Lending must have 2 ambiguity rules"

    # Must pass all validator checks with 0 violations
    violations = validate_manifest(lending_pack)
    assert len(violations) == 0, f"Lending manifest has validation violations: {violations}"
