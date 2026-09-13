from pathlib import Path

import pytest
import yaml

from app.main import app

CONTRACT_PATH = Path(__file__).parents[3] / "contract" / "openapi.yaml"


@pytest.fixture
def canonical_spec():
    assert CONTRACT_PATH.exists(), f"OpenAPI contract missing at {CONTRACT_PATH}"
    with open(CONTRACT_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_all_paths_and_operations_match_contract(canonical_spec):
    generated_openapi = app.openapi()

    canonical_paths = canonical_spec.get("paths", {})
    generated_paths = generated_openapi.get("paths", {})

    for path, path_item in canonical_paths.items():
        assert path in generated_paths, f"Missing path in generated OpenAPI: {path}"
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "delete", "patch"]:
                assert method in generated_paths[path], (
                    f"Missing method {method.upper()} for path {path} in generated OpenAPI"
                )
                expected_op_id = operation.get("operationId")
                actual_op_id = generated_paths[path][method].get("operationId")
                if expected_op_id:
                    assert actual_op_id == expected_op_id, (
                        f"Operation ID mismatch for {method.upper()} {path}: "
                        f"expected {expected_op_id}, got {actual_op_id}"
                    )


def test_core_schemas_present_and_valid(canonical_spec):
    generated_openapi = app.openapi()
    generated_schemas = generated_openapi.get("components", {}).get("schemas", {})
    canonical_schemas = canonical_spec.get("components", {}).get("schemas", {})

    expected_schemas = [
        "JourneyType",
        "Readiness",
        "JourneyStatus",
        "FieldStatus",
        "ErrorCode",
        "ErrorEnvelope",
        "JourneyPackSummary",
        "GoalFieldSpec",
        "JourneyPackDetail",
        "FieldState",
        "ProgressCounts",
        "JourneyStateResponse",
        "ActionOption",
        "RecommendationResponse",
        "SimulationPreview",
        "JourneyDiff",
        "EvidenceResponse",
        "ActionResponse",
        "JourneyListItem",
    ]

    for schema_name in expected_schemas:
        assert schema_name in canonical_schemas, f"Missing canonical schema: {schema_name}"
        assert schema_name in generated_schemas, f"Missing generated schema: {schema_name}"
