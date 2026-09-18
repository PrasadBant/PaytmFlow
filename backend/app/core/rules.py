from typing import Any

from app.core.dependencies import DependencyGraph
from app.core.models import (
    CoreAmbiguity,
    CoreFieldState,
    CoreFieldStatus,
    CoreProgressCounts,
)
from app.packs.contract import JourneyPackManifest


def is_field_applicable(
    field_key: str,
    manifest: JourneyPackManifest,
    goal: dict[str, Any],
) -> bool:
    for dep in manifest.dependencies:
        if dep.target == field_key and dep.condition:
            for k, pred in dep.condition.items():
                actual = goal.get(k)
                if isinstance(pred, dict):
                    if "eq" in pred and actual != pred["eq"]:
                        return False
                    if "neq" in pred and actual == pred["neq"]:
                        return False
                elif actual != pred:
                    return False
    return True


def derive_field_states(
    manifest: JourneyPackManifest,
    current_values: dict[str, Any],
    current_statuses: dict[str, CoreFieldStatus] | None = None,
    ambiguities: dict[str, CoreAmbiguity] | None = None,
    goal: dict[str, Any] | None = None,
) -> tuple[dict[str, CoreFieldState], CoreProgressCounts]:
    goal = goal or {}
    ambiguities = ambiguities or {}
    current_statuses = current_statuses or {}

    graph = DependencyGraph(manifest, goal)
    topological_order = graph.get_topological_order()

    state_schema_map = {f.key: f for f in manifest.state_schema}

    satisfiers: dict[str, str] = {}
    for action in manifest.actions:
        for s in action.satisfies:
            if s not in satisfiers:
                satisfiers[s] = action.action_id

    derived_states: dict[str, CoreFieldState] = {}

    for field_key in topological_order:
        spec = state_schema_map.get(field_key)
        if not spec:
            continue

        if not is_field_applicable(field_key, manifest, goal):
            derived_states[field_key] = CoreFieldState(
                key=field_key,
                label=spec.label,
                status=CoreFieldStatus.NOT_APPLICABLE,
                value=None,
                display_value="Not Applicable",
                explanation=None,
                resolve_action_id=None,
                mandatory=spec.mandatory,
                derived=spec.derived,
                display=False,
            )
            continue

        prereqs = graph.get_direct_prerequisites(field_key)
        unmet_prereqs = [
            p
            for p in prereqs
            if p in derived_states
            and derived_states[p].status
            not in [CoreFieldStatus.SATISFIED, CoreFieldStatus.NOT_APPLICABLE]
        ]

        if unmet_prereqs:
            blocking_labels = [
                state_schema_map[p].label for p in unmet_prereqs if p in state_schema_map
            ]
            explanation = f"Blocked by pending prerequisite: {', '.join(blocking_labels)}"
            derived_states[field_key] = CoreFieldState(
                key=field_key,
                label=spec.label,
                status=CoreFieldStatus.BLOCKED,
                value=current_values.get(field_key),
                display_value="Pending",
                explanation=spec.explanation or explanation,
                resolve_action_id=satisfiers.get(field_key),
                mandatory=spec.mandatory,
                derived=spec.derived,
                display=spec.display,
            )
        elif field_key in ambiguities:
            amb = ambiguities[field_key]
            derived_states[field_key] = CoreFieldState(
                key=field_key,
                label=spec.label,
                status=CoreFieldStatus.AMBIGUOUS,
                value=current_values.get(field_key),
                display_value="Needs Review",
                explanation=amb.reason,
                resolve_action_id=None,
                mandatory=spec.mandatory,
                derived=spec.derived,
                display=spec.display,
                ambiguity=amb,
            )
        else:
            val = current_values.get(field_key)
            explicit_status = current_statuses.get(field_key)

            if explicit_status == CoreFieldStatus.SATISFIED or (
                val is not None and val is not False
            ):
                if isinstance(val, bool):
                    display_val = "Verified" if val else "Pending"
                else:
                    display_val = str(val)
                if spec.type.value == "money" and isinstance(val, (int, float)):
                    display_val = f"₹{val:,.0f}"
                derived_states[field_key] = CoreFieldState(
                    key=field_key,
                    label=spec.label,
                    status=CoreFieldStatus.SATISFIED,
                    value=val,
                    display_value=display_val,
                    explanation=None,
                    resolve_action_id=None,
                    mandatory=spec.mandatory,
                    derived=spec.derived,
                    display=spec.display,
                )
            else:
                derived_states[field_key] = CoreFieldState(
                    key=field_key,
                    label=spec.label,
                    status=CoreFieldStatus.BLOCKED,
                    value=val,
                    display_value="Pending",
                    explanation=spec.explanation,
                    resolve_action_id=satisfiers.get(field_key),
                    mandatory=spec.mandatory,
                    derived=spec.derived,
                    display=spec.display,
                )

    applicable_fields = [
        f
        for f in derived_states.values()
        if f.mandatory and f.status != CoreFieldStatus.NOT_APPLICABLE
    ]
    completed = sum(1 for f in applicable_fields if f.status == CoreFieldStatus.SATISFIED)
    total = len(applicable_fields)
    pending = total - completed
    blockers = sum(
        1
        for f in applicable_fields
        if f.status == CoreFieldStatus.BLOCKED
    )

    progress = CoreProgressCounts(
        completed=completed,
        pending=pending,
        blockers=blockers,
        total=total,
    )

    return derived_states, progress
