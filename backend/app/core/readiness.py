from typing import Any

from app.core.models import (
    CoreFieldState,
    CoreFieldStatus,
    CoreReadiness,
)
from app.packs.contract import JourneyPackManifest


def _eval_condition(
    condition: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """Evaluate a single condition dictionary against context (field values and goal)."""
    # Format 1: {"field": "age", "op": "lt", "value": 18}
    if "field" in condition and ("op" in condition or "value" in condition):
        field_key = condition["field"]
        val = context.get(field_key)
        if val is None:
            return False

        op = condition.get("op", "eq")
        target_val = condition.get("value")

        if op == "eq":
            return bool(val == target_val)
        if op == "neq":
            return bool(val != target_val)
        if op == "lt":
            return bool(val < target_val)
        if op == "lte":
            return bool(val <= target_val)
        if op == "gt":
            return bool(val > target_val)
        if op == "gte":
            return bool(val >= target_val)
        if op == "in":
            target_list = target_val if isinstance(target_val, (list, tuple, set)) else [target_val]
            return val in target_list
        return False

    # Format 2: {"field_key": {"lt": 18}} or {"field_key": "some_value"}
    for key, expected in condition.items():
        actual = context.get(key)
        if actual is None:
            return False
        if isinstance(expected, dict):
            if "eq" in expected and actual != expected["eq"]:
                return False
            if "neq" in expected and actual == expected["neq"]:
                return False
            if "lt" in expected and not (actual < expected["lt"]):
                return False
            if "lte" in expected and not (actual <= expected["lte"]):
                return False
            if "gt" in expected and not (actual > expected["gt"]):
                return False
            if "gte" in expected and not (actual >= expected["gte"]):
                return False
            if "in" in expected and actual not in expected["in"]:
                return False
        elif actual != expected:
            return False

    return True


def evaluate_readiness(
    manifest: JourneyPackManifest,
    field_states: dict[str, CoreFieldState],
    goal: dict[str, Any] | None = None,
) -> CoreReadiness:
    """Pure deterministic evaluator returning exactly one CoreReadiness enum.

    State transition logic:
    1. DEAD_END: Any declared dead-end condition is met.
    2. NEEDS_REVIEW: Any field is in AMBIGUOUS status.
    3. NOT_READY: Any applicable mandatory field is not SATISFIED.
    4. READY: All applicable mandatory fields are SATISFIED.

    Never returns numeric scores or probabilities.
    """
    goal = goal or {}
    field_values = {k: f.value for k, f in field_states.items() if f.value is not None}
    eval_context = {**goal, **field_values}

    # 1. Dead end check
    dead_end_conditions = manifest.readiness_rules.dead_end_conditions or []
    for cond in dead_end_conditions:
        if _eval_condition(cond, eval_context):
            return CoreReadiness.DEAD_END

    # 2. Ambiguity check
    has_ambiguity = any(
        f.status == CoreFieldStatus.AMBIGUOUS or f.ambiguity is not None
        for f in field_states.values()
    )
    if has_ambiguity:
        return CoreReadiness.NEEDS_REVIEW

    # 3. Mandatory fields check
    mandatory_keys = manifest.readiness_rules.mandatory_fields
    for k in mandatory_keys:
        state = field_states.get(k)
        if not state:
            return CoreReadiness.NOT_READY
        if state.status == CoreFieldStatus.NOT_APPLICABLE:
            continue
        if state.status != CoreFieldStatus.SATISFIED:
            return CoreReadiness.NOT_READY

    # 4. All applicable mandatory fields are satisfied
    return CoreReadiness.READY
