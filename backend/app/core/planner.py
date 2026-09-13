from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from app.core.dependencies import DependencyGraph
from app.core.models import (
    CoreFieldStatus,
    CoreSnapshot,
)
from app.core.rules import derive_field_states
from app.packs.contract import ActionSpec, JourneyPackManifest


@dataclass(frozen=True)
class PlannedAction:
    action_id: str
    title: str
    kind: str
    why: str | None
    satisfies: list[str]
    preconditions: list[str]
    accepts: list[str] | None = None
    input_schema: list[dict[str, Any]] | None = None
    transitive_unblock_count: int = 0


@dataclass(frozen=True)
class PlanResult:
    actions: list[PlannedAction] = field(default_factory=list)
    minimum_path_length: int = 0
    is_path_found: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class NoPath(PlanResult):
    actions: list[PlannedAction] = field(default_factory=list)
    minimum_path_length: int = 0
    is_path_found: bool = False
    reason: str | None = "Unreachable mandatory field or no valid action path"


def plan(
    snapshot: CoreSnapshot,
    manifest: JourneyPackManifest,
) -> PlanResult:
    current_values = {k: f.value for k, f in snapshot.fields.items() if f.value is not None}
    current_statuses = {k: f.status for k, f in snapshot.fields.items()}

    current_states, _ = derive_field_states(
        manifest=manifest,
        current_values=current_values,
        current_statuses=current_statuses,
        goal=snapshot.goal,
    )

    # 1. Collect unsatisfied mandatory fields (excluding NOT_APPLICABLE)
    unsatisfied_mandatory = [
        f
        for f in current_states.values()
        if f.mandatory
        and f.status != CoreFieldStatus.SATISFIED
        and f.status != CoreFieldStatus.NOT_APPLICABLE
    ]

    if not unsatisfied_mandatory:
        return PlanResult(actions=[], minimum_path_length=0)

    # 2. For each, find the satisfying action (picking group primary if grouped)
    needed_actions: dict[str, ActionSpec] = {}
    action_groups = manifest.action_groups or {}

    for f in unsatisfied_mandatory:
        if f.derived:
            continue

        candidate_actions = [a for a in manifest.actions if f.key in a.satisfies]
        if not candidate_actions:
            return NoPath(reason=f"Mandatory non-derived field '{f.key}' has no satisfying action")

        selected_action = candidate_actions[0]
        if selected_action.action_group and selected_action.action_group in action_groups:
            group_spec = action_groups[selected_action.action_group]
            primary_act = next(
                (a for a in manifest.actions if a.action_id == group_spec.primary),
                selected_action,
            )
            selected_action = primary_act

        needed_actions[selected_action.action_id] = selected_action

    if not needed_actions:
        return PlanResult(actions=[], minimum_path_length=0)

    # 3. Calculate transitive unblock count for each needed action
    graph = DependencyGraph(manifest, snapshot.goal)
    action_unblock_counts: dict[str, int] = {}

    for act_id, act in needed_actions.items():
        # Fields transitively unblocked by fields satisfied by this action
        transitive_fields: set[str] = set()
        for s in act.satisfies:
            transitive_fields.update(graph.get_all_transitive_dependents(s))

        # Count how many other needed actions depend on these fields
        unblocked_actions = sum(
            1
            for other_id, other_act in needed_actions.items()
            if other_id != act_id and any(p in transitive_fields for p in other_act.preconditions)
        )
        action_unblock_counts[act_id] = unblocked_actions

    # 4. Build action-level DAG for needed actions
    action_adj: dict[str, set[str]] = defaultdict(set)
    action_in_degree: dict[str, int] = {a_id: 0 for a_id in needed_actions}

    # Action A -> Action B if A satisfies any precondition of B or prerequisite field of B
    field_to_satisfier: dict[str, str] = {}
    for act_id, act in needed_actions.items():
        for s in act.satisfies:
            field_to_satisfier[s] = act_id

    for b_id, b_act in needed_actions.items():
        # Find all prerequisites of b_act's preconditions
        required_fields = set(b_act.preconditions)
        for p in b_act.preconditions:
            required_fields.update(graph.get_all_transitive_prerequisites(p))

        for req_field in required_fields:
            if req_field in field_to_satisfier:
                a_id = field_to_satisfier[req_field]
                if a_id != b_id and b_id not in action_adj[a_id]:
                    action_adj[a_id].add(b_id)
                    action_in_degree[b_id] += 1

    # 5. Kahn topological sort with priority (-unblock_count, action_id)
    ordered_actions: list[PlannedAction] = []
    # Collect ready actions
    ready_queue = [act_id for act_id, deg in action_in_degree.items() if deg == 0]
    ready_queue.sort(key=lambda a_id: (-action_unblock_counts.get(a_id, 0), a_id))
    queue = deque(ready_queue)

    while queue:
        # Sort current ready candidates deterministically
        curr_id = queue.popleft()
        act_spec = needed_actions[curr_id]

        input_schema_dicts = (
            [f.model_dump() for f in act_spec.input_schema] if act_spec.input_schema else None
        )

        ordered_actions.append(
            PlannedAction(
                action_id=act_spec.action_id,
                title=act_spec.title,
                kind=act_spec.kind.value,
                why=act_spec.why,
                satisfies=act_spec.satisfies,
                preconditions=act_spec.preconditions,
                accepts=act_spec.accepts,
                input_schema=input_schema_dicts,
                transitive_unblock_count=action_unblock_counts.get(curr_id, 0),
            )
        )

        newly_ready = []
        for nxt_id in sorted(action_adj[curr_id]):
            action_in_degree[nxt_id] -= 1
            if action_in_degree[nxt_id] == 0:
                newly_ready.append(nxt_id)

        if newly_ready:
            # Insert and sort remaining queue
            combined = list(queue) + newly_ready
            combined.sort(key=lambda a_id: (-action_unblock_counts.get(a_id, 0), a_id))
            queue = deque(combined)

    if len(ordered_actions) < len(needed_actions):
        # Cycle detected among actions
        return NoPath(reason="Cycle detected in action dependencies")

    return PlanResult(
        actions=ordered_actions,
        minimum_path_length=len(ordered_actions),
        is_path_found=True,
    )
