from dataclasses import dataclass, field
from typing import Any

from app.core.models import (
    CoreFieldState,
    CoreFieldStatus,
    CoreProgressCounts,
    CoreReadiness,
    CoreSnapshot,
)
from app.core.readiness import evaluate_readiness
from app.core.rules import derive_field_states
from app.packs.contract import JourneyPackManifest


@dataclass(frozen=True)
class SimulationFieldItem:
    key: str
    label: str


@dataclass(frozen=True)
class SimulationActionItem:
    action_id: str
    title: str


@dataclass(frozen=True)
class CoreSimulationResult:
    newly_satisfied: list[SimulationFieldItem]
    newly_unlocked: list[SimulationActionItem]
    still_blocked: list[SimulationFieldItem]
    predicted_readiness: CoreReadiness
    progress_before: CoreProgressCounts
    progress_after: CoreProgressCounts
    simulated_fields: dict[str, CoreFieldState] = field(default_factory=dict)


def simulate(
    action_id: str,
    action_input: dict[str, Any] | None,
    snapshot: CoreSnapshot,
    manifest: JourneyPackManifest,
) -> CoreSimulationResult:
    action_obj = next((a for a in manifest.actions if a.action_id == action_id), None)
    if not action_obj:
        raise ValueError(f"Unknown action_id: {action_id}")

    current_values = {k: f.value for k, f in snapshot.fields.items() if f.value is not None}
    current_statuses = {k: f.status for k, f in snapshot.fields.items()}

    # Extract new values from input or simulation defaults
    applied_values: dict[str, Any] = {}
    defaults = manifest.simulation_defaults or {}

    for s in action_obj.satisfies:
        if action_input and s in action_input:
            applied_values[s] = action_input[s]
        elif action_input and "evidence_id" in action_input:
            # Evidence action default value
            applied_values[s] = defaults.get(s, True)
        elif action_input and len(action_input) == 1 and s not in action_input:
            # Single value in input assigned to field
            val = next(iter(action_input.values()))
            applied_values[s] = val
        else:
            applied_values[s] = defaults.get(s, True)

    new_values = {**current_values, **applied_values}

    # Derive new states
    new_states, progress_after = derive_field_states(
        manifest=manifest,
        current_values=new_values,
        goal=snapshot.goal,
    )

    # Compute progress before
    _, progress_before = derive_field_states(
        manifest=manifest,
        current_values=current_values,
        current_statuses=current_statuses,
        goal=snapshot.goal,
    )

    # Calculate newly satisfied
    newly_satisfied = []
    for s_field in action_obj.satisfies:
        if s_field in new_states and new_states[s_field].status == CoreFieldStatus.SATISFIED:
            prev_status = current_statuses.get(s_field)
            if prev_status != CoreFieldStatus.SATISFIED:
                newly_satisfied.append(
                    SimulationFieldItem(key=s_field, label=new_states[s_field].label)
                )

    # Calculate newly unlocked actions
    before_satisfied_keys = {
        k
        for k, f in snapshot.fields.items()
        if f.status in [CoreFieldStatus.SATISFIED, CoreFieldStatus.NOT_APPLICABLE]
    }
    after_satisfied_keys = {
        k
        for k, f in new_states.items()
        if f.status in [CoreFieldStatus.SATISFIED, CoreFieldStatus.NOT_APPLICABLE]
    }

    newly_unlocked = []
    for act in manifest.actions:
        if act.action_id != action_id:
            was_unlocked = all(p in before_satisfied_keys for p in act.preconditions)
            is_unlocked = all(p in after_satisfied_keys for p in act.preconditions)
            if is_unlocked and not was_unlocked:
                newly_unlocked.append(
                    SimulationActionItem(action_id=act.action_id, title=act.title)
                )

    # Calculate still blocked fields
    still_blocked = []
    for k, state in new_states.items():
        if state.mandatory and state.status == CoreFieldStatus.BLOCKED:
            still_blocked.append(SimulationFieldItem(key=k, label=state.label))

    predicted_readiness = evaluate_readiness(manifest, new_states)

    return CoreSimulationResult(
        newly_satisfied=newly_satisfied,
        newly_unlocked=newly_unlocked,
        still_blocked=still_blocked,
        predicted_readiness=predicted_readiness,
        progress_before=progress_before,
        progress_after=progress_after,
        simulated_fields=new_states,
    )
