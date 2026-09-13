from app.core.dependencies import DependencyGraph
from app.core.models import (
    CoreFieldChange,
    CoreFieldState,
    CoreFieldStatus,
    CoreJourneyDiff,
    CoreProgressCounts,
    CoreProgressDiff,
    CoreReadinessDiff,
    CoreSnapshot,
)
from app.packs.contract import ActionSpec, JourneyPackManifest


def _is_action_active(
    action: ActionSpec,
    fields: dict[str, CoreFieldState],
) -> bool:
    """An action is active (available to execute) if all preconditions are satisfied

    and at least one field it satisfies is not yet satisfied.
    """
    preconditions_met = all(
        fields.get(p) is not None
        and fields[p].status in [CoreFieldStatus.SATISFIED, CoreFieldStatus.NOT_APPLICABLE]
        for p in action.preconditions
    )
    if not preconditions_met:
        return False

    has_unsatisfied_target = any(
        fields.get(s) is None or fields[s].status != CoreFieldStatus.SATISFIED
        for s in action.satisfies
    )
    return has_unsatisfied_target


def _compute_snapshot_progress(
    snapshot: CoreSnapshot,
    manifest: JourneyPackManifest | None,
) -> CoreProgressCounts:
    applicable_fields = [
        f
        for f in snapshot.fields.values()
        if f.mandatory and f.status != CoreFieldStatus.NOT_APPLICABLE
    ]
    completed = sum(1 for f in applicable_fields if f.status == CoreFieldStatus.SATISFIED)
    total = len(applicable_fields)
    pending = total - completed

    if manifest:
        graph = DependencyGraph(manifest, snapshot.goal)
        blockers = sum(
            1
            for f in applicable_fields
            if f.status == CoreFieldStatus.BLOCKED
            and all(
                snapshot.fields.get(p) is not None
                and snapshot.fields[p].status
                in [CoreFieldStatus.SATISFIED, CoreFieldStatus.NOT_APPLICABLE]
                for p in graph.get_direct_prerequisites(f.key)
            )
        )
    else:
        blockers = sum(1 for f in applicable_fields if f.status == CoreFieldStatus.BLOCKED)

    return CoreProgressCounts(
        completed=completed,
        pending=pending,
        blockers=blockers,
        total=total,
    )


def compute_diff(
    snapshot_a: CoreSnapshot,
    snapshot_b: CoreSnapshot,
    manifest: JourneyPackManifest | None = None,
    direct_fields: set[str] | list[str] | None = None,
    cause: str | None = None,
) -> CoreJourneyDiff:
    """Compute pure deterministic diff between two journey snapshots."""
    direct_field_set = set(direct_fields) if direct_fields else None
    fields_changed: list[CoreFieldChange] = []

    # Check all fields in snapshot_b
    all_keys = list(snapshot_b.fields.keys())
    # Also add any keys in snapshot_a not in snapshot_b
    for k in snapshot_a.fields:
        if k not in all_keys:
            all_keys.append(k)

    for key in all_keys:
        a_field = snapshot_a.fields.get(key)
        b_field = snapshot_b.fields.get(key)

        if a_field is None and b_field is not None:
            # Field added
            cascaded = (
                (key not in direct_field_set) if direct_field_set is not None else b_field.derived
            )
            fields_changed.append(
                CoreFieldChange(
                    key=key,
                    label=b_field.label,
                    from_status=CoreFieldStatus.BLOCKED,
                    to_status=b_field.status,
                    display_value=b_field.display_value,
                    cause=cause,
                    cascaded=cascaded,
                )
            )
        elif a_field is not None and b_field is not None:
            # Compare state changes
            is_changed = (
                a_field.status != b_field.status
                or a_field.value != b_field.value
                or a_field.display_value != b_field.display_value
                or (a_field.ambiguity is not None) != (b_field.ambiguity is not None)
            )
            if is_changed:
                cascaded = (
                    (key not in direct_field_set)
                    if direct_field_set is not None
                    else b_field.derived
                )
                fields_changed.append(
                    CoreFieldChange(
                        key=key,
                        label=b_field.label,
                        from_status=a_field.status,
                        to_status=b_field.status,
                        display_value=b_field.display_value,
                        cause=cause,
                        cascaded=cascaded,
                    )
                )

    # Actions unlocked / removed
    actions_unlocked: list[str] = []
    actions_removed: list[str] = []
    if manifest:
        active_a = {
            a.action_id for a in manifest.actions if _is_action_active(a, snapshot_a.fields)
        }
        active_b = {
            a.action_id for a in manifest.actions if _is_action_active(a, snapshot_b.fields)
        }
        actions_unlocked = sorted(active_b - active_a)
        actions_removed = sorted(active_a - active_b)

    # Readiness diff
    readiness_diff = CoreReadinessDiff(
        from_readiness=snapshot_a.readiness,
        to_readiness=snapshot_b.readiness,
    )

    # Progress diff
    prog_a = _compute_snapshot_progress(snapshot_a, manifest)
    prog_b = _compute_snapshot_progress(snapshot_b, manifest)
    progress_diff = CoreProgressDiff(
        from_progress=prog_a,
        to_progress=prog_b,
    )

    return CoreJourneyDiff(
        from_version=snapshot_a.version_number,
        to_version=snapshot_b.version_number,
        fields_changed=fields_changed,
        actions_unlocked=actions_unlocked,
        actions_removed=actions_removed,
        readiness=readiness_diff,
        progress=progress_diff,
    )
