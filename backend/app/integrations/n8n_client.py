"""Outbound webhook dispatcher to the existing n8n Cloud production
workflow (https://prasadbant.app.n8n.cloud/webhook/paytmflow-events).

Fires on five Review Center lifecycle events - REVIEW_REQUIRED,
CUSTOMER_ACTION_REQUIRED, EVIDENCE_UPLOADED, JOURNEY_RESOLVED, ESCALATED -
each mapped 1:1 onto an existing audit event this codebase already writes
(see app/audit/events.py). n8n then fans these out to Slack/email; this
module only ever sends a notification, never receives a decision back -
n8n cannot influence journey state, exactly like every other AI/notification
integration in this codebase.

Also fires JOURNEY_COMPLETED - a sixth event, orthogonal to the five above:
those are all Review Center case lifecycle events (require a real
ReviewCaseModel), while JOURNEY_COMPLETED fires the moment a journey's OWN
readiness reaches READY (app/core/readiness.py's evaluate_readiness), with
or without ever having gone through review. See
app/services/journey_service.py's apply_action/submit_clarification for
where it's queued - each guards it on the pre-mutation vs post-mutation
readiness value so it fires exactly once per READY transition, never on a
no-op recalculation. As of 2026-09-20 the live n8n workflow's own router
does NOT yet have a branch for this event name - see the delivery notes
recorded for this change. It is still safe to send: the workflow's "Valid
Payload?" node only requires the shared fields to be non-empty, so an
unrecognized `event` value is a rejected/no-route branch, not a crash - the
same "never blocks or breaks the request that triggered it" guarantee
covers this like every other event.

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

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import NotificationFailureModel

logger = structlog.get_logger(__name__)

_PENDING_KEY = "_pending_n8n_events"

VALID_EVENT_TYPES = frozenset(
    {
        "REVIEW_REQUIRED",
        "CUSTOMER_ACTION_REQUIRED",
        "EVIDENCE_UPLOADED",
        "JOURNEY_RESOLVED",
        "ESCALATED",
        "JOURNEY_COMPLETED",
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


def discard_n8n_events(db: AsyncSession) -> None:
    """Drops events queued on `db` - call after a rollback, since `db.info`
    outlives the transaction that queued them."""
    db.info.pop(_PENDING_KEY, None)


async def flush_n8n_events(db: AsyncSession) -> None:
    """Dispatches every event queued on `db` since the last flush. Call
    this ONLY immediately after the governing `await db.commit()` for
    whichever write(s) queued them has already succeeded.

    Each event gets bounded retries (see `_dispatch`); one that still fails
    is written to `notification_failures` for later redelivery. Never raises.

    This runs inside the HTTP request that made the write, so all events share
    one N8N_FLUSH_BUDGET_SECONDS budget: a down or slow n8n can delay the
    response by at most that much (not attempts x timeout per event), keeping
    it clear of proxy timeouts that would make a user retry a committed write.
    Events that do not fit are recorded for redelivery instead."""
    events = db.info.pop(_PENDING_KEY, None)
    if not events:
        return
    if not settings.N8N_ENABLED or not settings.N8N_WEBHOOK_URL:
        return
    deadline = time.monotonic() + settings.N8N_FLUSH_BUDGET_SECONDS
    for event in events:
        try:
            await _dispatch(event, deadline)
        except N8nDeliveryError as exc:
            await _record_failure(db, event, exc)
        except Exception as exc:  # defense-in-depth: see module docstring invariant 2 -
            # this must hold even if _dispatch itself has a bug, not only for
            # the httpx errors it already classifies.
            logger.warning(
                "n8n_webhook_unexpected_dispatch_error",
                event_type=event.get("event"),
                event_id=event.get("event_id"),
                error=str(exc),
            )
            await _record_failure(
                db, event, N8nDeliveryError(FAILURE_PERMANENT, 1, None, f"unexpected: {exc}")
            )


FAILURE_TRANSIENT = "TRANSIENT_EXHAUSTED"
FAILURE_PERMANENT = "PERMANENT"
# Status codes worth retrying; any other non-2xx (bad payload, bad secret,
# wrong URL) fails identically on every attempt.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class N8nDeliveryError(Exception):
    def __init__(self, kind: str, attempts: int, status_code: int | None, error: str) -> None:
        super().__init__(error)
        self.kind = kind
        self.attempts = attempts
        self.status_code = status_code
        self.error = error[:500]


async def _dispatch(event: dict[str, Any], deadline: float | None = None) -> None:
    """POSTs one event with up to N8N_MAX_ATTEMPTS tries and exponential
    backoff, never past `deadline` (time.monotonic()). Every try carries the
    same event_id (body and Idempotency-Key header), which the workflow
    deduplicates on, so a retry after a lost response cannot double-notify.
    Raises N8nDeliveryError when it gives up."""
    headers = {"Content-Type": "application/json", "Idempotency-Key": str(event["event_id"])}
    if settings.N8N_WEBHOOK_SECRET:
        headers[settings.N8N_WEBHOOK_HEADER_NAME] = settings.N8N_WEBHOOK_SECRET

    max_attempts = max(1, settings.N8N_MAX_ATTEMPTS)
    status_code: int | None = None
    error = ""
    attempts = 0

    def remaining() -> float:
        return float("inf") if deadline is None else deadline - time.monotonic()

    async with httpx.AsyncClient(timeout=float(settings.N8N_TIMEOUT_SECONDS)) as client:
        for attempt in range(1, max_attempts + 1):
            if remaining() <= 0:
                error = error or "flush time budget exhausted before sending"
                break
            attempts = attempt
            timeout = min(float(settings.N8N_TIMEOUT_SECONDS), remaining())
            try:
                response = await client.post(
                    settings.N8N_WEBHOOK_URL, headers=headers, json=event, timeout=timeout
                )
            except httpx.TransportError as exc:  # timeouts, connect/read errors
                # Never log the webhook secret; httpx errors carry the URL only.
                status_code, error = None, f"{type(exc).__name__}: {exc}"
            else:
                status_code = response.status_code
                if 200 <= status_code < 300:
                    logger.info(
                        "n8n_webhook_dispatched",
                        event_type=event.get("event"),
                        event_id=event.get("event_id"),
                        status_code=status_code,
                        attempt=attempt,
                    )
                    return
                error = f"HTTP {status_code}"
                if status_code not in _RETRYABLE_STATUS:
                    logger.warning(
                        "n8n_webhook_rejected",
                        event_type=event.get("event"),
                        event_id=event.get("event_id"),
                        status_code=status_code,
                    )
                    raise N8nDeliveryError(FAILURE_PERMANENT, attempt, status_code, error)
            logger.warning(
                "n8n_webhook_dispatch_failed",
                event_type=event.get("event"),
                event_id=event.get("event_id"),
                attempt=attempt,
                max_attempts=max_attempts,
                error=error,
            )
            if attempt < max_attempts:
                backoff = settings.N8N_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
                if backoff >= remaining():
                    break
                await asyncio.sleep(backoff)
    raise N8nDeliveryError(FAILURE_TRANSIENT, attempts, status_code, error)


async def _record_failure(db: AsyncSession, event: dict[str, Any], exc: N8nDeliveryError) -> None:
    """Upserts the durable failure row in its OWN session, so a problem here
    can never roll back or expire the caller's already-committed objects."""
    bind = db.bind if isinstance(db, AsyncSession) else None
    if bind is None:
        logger.error("n8n_failure_not_recorded", event_id=event.get("event_id"), reason="no_bind")
        return
    try:
        async with AsyncSession(bind, expire_on_commit=False) as record_db:
            await _upsert_failure(record_db, event, exc)
            await record_db.commit()
        logger.warning(
            "n8n_failure_recorded",
            event_type=event.get("event"),
            event_id=event.get("event_id"),
            failure_kind=exc.kind,
            attempts=exc.attempts,
        )
    except Exception as record_exc:
        logger.error(
            "n8n_failure_not_recorded",
            event_id=event.get("event_id"),
            error=str(record_exc)[:300],
        )


async def _upsert_failure(db: AsyncSession, event: dict[str, Any], exc: N8nDeliveryError) -> None:
    row = await db.get(NotificationFailureModel, str(event["event_id"]))
    if row is None:
        db.add(
            NotificationFailureModel(
                event_id=str(event["event_id"]),
                event_type=str(event.get("event", "")),
                journey_id=str(event.get("journey_id", "")),
                payload=event,
                failure_kind=exc.kind,
                attempts=exc.attempts,
                last_status_code=exc.status_code,
                last_error=exc.error,
            )
        )
    else:
        row.failure_kind = exc.kind
        row.attempts += exc.attempts
        row.last_status_code = exc.status_code
        row.last_error = exc.error


async def redeliver_failed_events(db: AsyncSession, limit: int = 50) -> dict[str, int]:
    """Retries undelivered TRANSIENT_EXHAUSTED events with their original
    event_id. PERMANENT failures are left for a human (fix the payload,
    secret or URL first). Run via `python -m app.integrations.n8n_redeliver`.

    Rows are claimed one at a time with FOR UPDATE SKIP LOCKED and held until
    that row's outcome is committed, so two concurrent runs never send the same
    event; each row is tried at most once per run."""
    counts = {"delivered": 0, "failed": 0}
    if not settings.N8N_ENABLED or not settings.N8N_WEBHOOK_URL:
        return counts
    tried: list[str] = []
    for _ in range(limit):
        stmt = (
            select(NotificationFailureModel)
            .where(
                NotificationFailureModel.delivered_at.is_(None),
                NotificationFailureModel.failure_kind == FAILURE_TRANSIENT,
            )
            .order_by(NotificationFailureModel.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if tried:
            stmt = stmt.where(NotificationFailureModel.event_id.not_in(tried))
        row = await db.scalar(stmt)
        if row is None:
            break
        tried.append(row.event_id)
        try:
            await _dispatch(dict(row.payload))
        except N8nDeliveryError as exc:
            await _upsert_failure(db, row.payload, exc)
            counts["failed"] += 1
        else:
            row.delivered_at = datetime.now(UTC)
            counts["delivered"] += 1
        await db.commit()
    return counts
