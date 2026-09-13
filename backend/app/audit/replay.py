from uuid import UUID

from app.audit.events import AuditEventType
from app.core.models import (
    CoreAmbiguity,
    CoreFieldStatus,
    CoreSnapshot,
)
from app.core.readiness import evaluate_readiness
from app.core.rules import derive_field_states
from app.db.models import AuditEventModel
from app.packs.contract import JourneyPackManifest


def replay_journey(
    journey_id: UUID,
    events: list[AuditEventModel],
    manifest: JourneyPackManifest,
) -> CoreSnapshot:
    """Deterministically reconstructs the current journey snapshot by replaying the audit log."""
    if not events:
        raise ValueError(f"No audit events found for journey {journey_id}")

    sorted_events = sorted(events, key=lambda e: e.created_at)

    created_event = next(
        (e for e in sorted_events if e.event_type == AuditEventType.JOURNEY_CREATED),
        None,
    )
    if not created_event:
        raise ValueError(f"No JOURNEY_CREATED event found in audit log for journey {journey_id}")

    goal = created_event.payload.get("goal", {})
    initial_snapshot_id = UUID(created_event.payload["initial_snapshot_id"])
    current_values = dict(created_event.payload.get("initial_values", {}))
    current_version = 1
    current_snapshot_id = initial_snapshot_id
    ambiguities: dict[str, CoreAmbiguity] = {}

    for event in sorted_events:
        if event.event_type == AuditEventType.ACTION_EXECUTED:
            new_values = event.payload.get("new_values", {})
            current_values.update(new_values)
            current_version = event.payload.get("version_number", current_version + 1)
            current_snapshot_id = UUID(event.payload["snapshot_id"])

        elif event.event_type == AuditEventType.CLARIFICATION_REQUESTED:
            ambiguity_id = event.payload["ambiguity_id"]
            field_key = event.payload["field_key"]
            rule = next(
                (r for r in manifest.ambiguity_rules if r.ambiguity_id == ambiguity_id),
                None,
            )
            ambiguities[field_key] = CoreAmbiguity(
                ambiguity_id=ambiguity_id,
                field=field_key,
                reason=rule.reason if rule else "Ambiguity flagged in evidence",
                question=event.payload.get("question", rule.question if rule else ""),
                answer_type=rule.answer_type.value if rule else "TEXT",
            )

        elif event.event_type == AuditEventType.CLARIFICATION_ANSWERED:
            field_key = event.payload["field_key"]
            user_response = event.payload.get("user_response", {})
            # Extract resolution value from response dictionary
            resp_val = user_response.get(
                field_key,
                user_response.get("value", user_response.get("selected_value")),
            )
            if resp_val is None and len(user_response) == 1:
                resp_val = next(iter(user_response.values()))

            if resp_val is not None:
                current_values[field_key] = resp_val

            ambiguities.pop(field_key, None)
            current_version += 1
            current_snapshot_id = UUID(event.payload["snapshot_id"])

        # Note: ACTION_REJECTED, EVIDENCE_UPLOADED, and STATE_TRANSITION
        # do not mutate underlying field values.

    field_states, _ = derive_field_states(
        manifest=manifest,
        current_values=current_values,
        ambiguities=ambiguities,
        goal=goal,
    )
    readiness = evaluate_readiness(
        manifest=manifest,
        field_states=field_states,
        goal=goal,
    )

    pending_clarification = next(
        (f for f in field_states.values() if f.status == CoreFieldStatus.AMBIGUOUS),
        None,
    )

    return CoreSnapshot(
        snapshot_id=current_snapshot_id,
        journey_id=journey_id,
        journey_type=manifest.metadata.journey_type.value,
        version_number=current_version,
        readiness=readiness,
        fields=field_states,
        goal=goal,
        pending_clarification=pending_clarification,
    )
