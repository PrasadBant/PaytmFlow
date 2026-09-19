"""Outbound webhook dispatcher to the existing n8n Cloud production
workflow (https://prasadbant.app.n8n.cloud/webhook/paytmflow-events).

Fires on five Review Center lifecycle events - REVIEW_REQUIRED,
CUSTOMER_ACTION_REQUIRED, EVIDENCE_UPLOADED, JOURNEY_RESOLVED, ESCALATED -
each mapped 1:1 onto an existing audit event this codebase already writes
(see app/audit/events.py). n8n then fans these out to Slack/email; this
module only ever sends a notification, never receives a decision back -
n8n cannot influence journey state, exactly like every other AI/notification
integration in this codebase.

Two invariants enforced by design, not by convention:

1. **Never notify before the write is durable.** `queue_event()` only
   appends an event to the CURRENT DB session's `.info` dict - pure
   in-memory bookkeeping, zero I/O. The caller must call `flush_n8n_events()`
   AFTER its own `await db.commit()` succeeds. If the transaction rolls back
   instead, the queued events are simply discarded with the session - no
   notification for a write that never happened.
2. **n8n being down/slow/misconfigured must never fail the request it's
   attached to.** `flush_n8n_events()` swallows every dispatch error
   (logged, never raised) - same "advisory, never a point of failure"
   principle already applied to Sarvam's fallback chain.

Duplicate protection: `flush_n8n_events()` POPS the queued list, so a given
session's events can only ever be flushed once - calling it twice (e.g. a
bug in a caller) sends nothing the second time. The receiving workflow
ALSO deduplicates on its own side (a `dedup_key` derived from `event_id`,
falling back to `case_id|event|timestamp`) via a lookup table, so a
resend after a network retry is safe on both ends.

Payload schema (verified directly against the real, live n8n workflow via
its own REST API on 2026-09-19 - its "Normalize Event"/"Valid Payload?"
nodes were inspected node-by-node, not guessed): every event sends
`event` (one of the five type strings below), `event_id`, `case_id`,
`journey_id`, `customer_id`, `customer_email`, `message`, `timestamp`
(ISO 8601). `event`/`case_id`/`journey_id`/`event_id`/`timestamp` are
enforced non-empty by the workflow's own "Valid Payload?" node - a request
missing any of them is rejected with a real, verified `400
{"success": false, "status": "invalid_payload"}` from its "Respond
Invalid" node (confirmed by triggering this deliberately while fixing
this integration). `customer_email` is optional contact data: the session
model (app/db/models.py's SessionModel.meta) may hold a
customer-supplied email, set at journey creation (see
CreateJourneyRequest.customer_email) - callers that know the owning
session (app/services/review_service.py's resolve_case/
request_information) look it up and thread it through here. It is sent
as an empty string whenever no email was ever supplied for that session,
which the workflow's "Email Customer" nodes treat as "nothing to send to"
(no customer notification fires, but Slack/reviewer-facing notifications
are unaffected). This is a real, non-fabricated address only - never
invented, never required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = structlog.get_logger(__name__)

_PENDING_KEY = "_pending_n8n_events"

VALID_EVENT_TYPES = frozenset(
    {
        "REVIEW_REQUIRED",
        "CUSTOMER_ACTION_REQUIRED",
        "EVIDENCE_UPLOADED",
        "JOURNEY_RESOLVED",
        "ESCALATED",
    }
)


def queue_event(
    db: AsyncSession,
    event_type: str,
    journey_id: UUID,
    *,
    case_id: str,
    message: str,
    customer_id: str | None = None,
    customer_email: str = "",
) -> None:
    """Queues an n8n notification on `db` - no I/O, always safe to call
    even when N8N_ENABLED is false (the no-op gate lives in flush).

    `case_id` and `message` are required keyword args, not optional
    extras: the receiving workflow's own "Valid Payload?" node rejects any
    event missing a non-empty case_id (HTTP 400), and its Slack/email
    notification nodes render `message` directly as the human-readable
    body - an empty or missing one would silently produce a blank
    notification. Every call site must supply a real, non-fabricated
    value for both (e.g. the case's own reason_title, an evidence
    upload's doc_type, or the reviewer-supplied resolution/escalation
    reason - never invented text).
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Unknown n8n event_type: {event_type!r}")
    if not case_id:
        raise ValueError("n8n event requires a non-empty case_id (see queue_event docstring)")
    events: list[dict[str, Any]] = db.info.setdefault(_PENDING_KEY, [])
    events.append(
        {
            "event": event_type,
            "event_id": str(uuid.uuid4()),
            "case_id": case_id,
            "journey_id": str(journey_id),
            "customer_id": str(customer_id) if customer_id else "",
            "customer_email": customer_email,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


async def flush_n8n_events(db: AsyncSession) -> None:
    """Dispatches every event queued on `db` since the last flush. Call
    this ONLY immediately after the governing `await db.commit()` for
    whichever write(s) queued them has already succeeded."""
    events = db.info.pop(_PENDING_KEY, None)
    if not events:
        return
    if not settings.N8N_ENABLED or not settings.N8N_WEBHOOK_URL:
        return
    for event in events:
        try:
            await _dispatch(event)
        except Exception as exc:  # defense-in-depth: see module docstring invariant 2 -
            # this must hold even if _dispatch itself has a bug, not only for
            # the httpx.HTTPError subset it already catches internally.
            logger.warning(
                "n8n_webhook_unexpected_dispatch_error",
                event_type=event.get("event"),
                event_id=event.get("event_id"),
                error=str(exc),
            )


async def _dispatch(event: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json"}
    if settings.N8N_WEBHOOK_SECRET:
        headers[settings.N8N_WEBHOOK_HEADER_NAME] = settings.N8N_WEBHOOK_SECRET

    try:
        async with httpx.AsyncClient(timeout=float(settings.N8N_TIMEOUT_SECONDS)) as client:
            response = await client.post(settings.N8N_WEBHOOK_URL, headers=headers, json=event)
        logger.info(
            "n8n_webhook_dispatched",
            event_type=event.get("event"),
            event_id=event.get("event_id"),
            status_code=response.status_code,
        )
    except httpx.HTTPError as exc:
        # Never log the webhook secret or raise - a notification failure
        # must never surface as a failure of the request that triggered it.
        logger.warning(
            "n8n_webhook_dispatch_failed",
            event_type=event.get("event"),
            event_id=event.get("event_id"),
            error=str(exc),
        )
