"""Outbound webhook dispatcher to the existing n8n Cloud production
workflow (the configured N8N_WEBHOOK_URL endpoint).

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

Delivery guarantees, enforced by design rather than convention:

1. **The event commits with the change that emits it.** `queue_event()` adds
   an `n8n_outbox` row (status PENDING, full payload, a fresh `event_id`) to
   the CALLER's session. It becomes durable in the same COMMIT as the
   business write, and a rollback removes it with that write - so there is
   never a notification for a change that did not happen, and a committed
   change never loses its notification to a crash or cancellation.
2. **No HTTP inside a database transaction.** A dispatcher claims a row in a
   short transaction (FOR UPDATE SKIP LOCKED, then a `lease_until` and a
   random `lease_token`), commits, sends, and records the outcome in a new
   transaction only if it still holds that lease token. A row whose
   dispatcher died is reclaimed once its lease expires.
3. **n8n being down/slow/misconfigured must never fail the request it's
   attached to.** `flush_n8n_events()` (called after the caller's commit)
   tries the request's own events within N8N_FLUSH_BUDGET_SECONDS and never
   raises; anything not delivered stays PENDING for the background sweeper
   (`start_outbox_sweeper`, every N8N_OUTBOX_SWEEP_SECONDS) or the manual
   `python -m app.integrations.n8n_redeliver`.

Delivery is AT LEAST ONCE. Every try, redispatch and recovery of an event
sends the same `event_id` (body and `Idempotency-Key` header). If n8n accepts
an event but the success is never recorded (lost response, crash before the
outcome commits), the event is sent again with that same id. Whether that
produces a second Slack/email notification depends on the receiving workflow
deduplicating on `event_id`; that is NOT verified from this repository.

Data minimisation: an undelivered row keeps the full payload, because the
notification must be reproduced exactly. Once DELIVERED or EXPIRED only
REDELIVERY_REQUIRED_FIELDS remain (`customer_email`, `customer_id` and
`message` are removed, `redacted_at` set). Error text is stripped of URLs and
secret-like values and capped at 500 characters. Payloads are never logged.
`purge_outbox` applies N8N_FAILURE_RETENTION_DAYS (see app/config.py).

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
import email.utils
import math
import re
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.config import settings
from app.db.models import N8nOutboxModel

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

STATUS_PENDING = "PENDING"
STATUS_DELIVERED = "DELIVERED"
STATUS_PERMANENT = "PERMANENT"
STATUS_EXPIRED = "EXPIRED"

# How one dispatch ended (N8nDeliveryError.kind).
FAILURE_TRANSIENT = "TRANSIENT_EXHAUSTED"
FAILURE_PERMANENT = "PERMANENT"

# Minimum redelivery contract: the fields the workflow's "Valid Payload?" node
# requires non-empty. They are all a DELIVERED/EXPIRED row keeps.
REDELIVERY_REQUIRED_FIELDS = ("event", "event_id", "case_id", "journey_id", "timestamp")
PERSONAL_FIELDS = ("customer_email", "customer_id", "message")

# Status codes worth retrying; any other non-2xx (bad payload, bad secret,
# wrong URL) fails identically on every attempt.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})
_RETRY_AFTER_STATUS = frozenset({429, 503})
# Between dispatches of a still-PENDING event: 30s, 60s, ... capped at 1h.
_REDISPATCH_BASE_SECONDS = 30.0
_REDISPATCH_MAX_SECONDS = 3600.0
# A dispatch gives up this long before its lease ends, so it never outlives it.
_LEASE_MARGIN_SECONDS = 5.0
_PURGE_BATCH = 500

_Bind = AsyncEngine | AsyncConnection

_URL_RE = re.compile(r"[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
_SECRETISH_RE = re.compile(
    r"\b(secret|token|password|passwd|api[_-]?key|authorization|bearer)\b\s*[:=]?\s*\S+",
    re.IGNORECASE,
)


def _enabled() -> bool:
    return bool(settings.N8N_ENABLED and settings.N8N_WEBHOOK_URL)


def _now() -> datetime:
    return datetime.now(UTC)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _safe_error(text: str) -> str:
    """Error text fit to store and log: no webhook URL/secret, no URLs, no
    secret-looking values, at most 500 characters."""
    for literal in (settings.N8N_WEBHOOK_URL, settings.N8N_WEBHOOK_SECRET):
        if literal:
            text = text.replace(literal, "<redacted>")
    text = _URL_RE.sub("<url>", text)
    text = _SECRETISH_RE.sub(r"\1=<redacted>", text)
    return text[:500]


def _minimal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload.get(key, "") for key in REDELIVERY_REQUIRED_FIELDS}


def _redact(row: N8nOutboxModel, now: datetime) -> None:
    row.payload = _minimal_payload(dict(row.payload))
    row.redacted_at = now


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
    """Adds an n8n notification to the caller's session as a PENDING
    `n8n_outbox` row: it commits or rolls back with the caller's own write.
    No I/O; call `flush_n8n_events()` after the commit for prompt delivery.
    A no-op (nothing stored) while N8N_ENABLED is false or no URL is set.

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
    if not _enabled():
        return
    event = {
        "event": event_type,
        "event_id": str(uuid.uuid4()),
        "case_id": case_id,
        "journey_id": str(journey_id),
        "customer_id": str(customer_id) if customer_id else "",
        "customer_email": customer_email,
        "message": message,
        "timestamp": _now().isoformat(),
    }
    db.add(
        N8nOutboxModel(
            event_id=event["event_id"],
            event_type=event_type,
            journey_id=event["journey_id"],
            payload=event,
            status=STATUS_PENDING,
            attempts=0,
            last_error="",
            next_attempt_at=_now(),
        )
    )
    db.info.setdefault(_PENDING_KEY, []).append(event["event_id"])


def discard_n8n_events(db: AsyncSession) -> None:
    """Forgets the event ids queued on `db` - call after a rollback, since
    `db.info` outlives the transaction (the rows themselves rolled back)."""
    db.info.pop(_PENDING_KEY, None)


async def flush_n8n_events(db: AsyncSession) -> None:
    """Tries to deliver the events queued on `db` since the last flush. Call
    this ONLY immediately after the governing `await db.commit()` succeeded.

    Runs inside the HTTP request that made the write, so all its events share
    one N8N_FLUSH_BUDGET_SECONDS budget: a down or slow n8n delays the response
    by at most that much. Whatever is not delivered stays PENDING in the
    outbox for the sweeper. Never raises (except cancellation, which leaves
    the events recoverable)."""
    event_ids: list[str] | None = db.info.pop(_PENDING_KEY, None)
    if not event_ids or not _enabled():
        return
    bind = getattr(db, "bind", None)
    if bind is None:
        logger.error("n8n_outbox_flush_skipped", reason="no_bind", events=len(event_ids))
        return
    deadline = time.monotonic() + settings.N8N_FLUSH_BUDGET_SECONDS
    for event_id in event_ids:
        if deadline - time.monotonic() <= 0:
            logger.info("n8n_outbox_deferred", event_id=event_id, reason="flush_budget_exhausted")
            continue
        await _process_one(bind, deadline, event_id=event_id)


class N8nDeliveryError(Exception):
    def __init__(
        self,
        kind: str,
        attempts: int,
        status_code: int | None,
        error: str,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(error)
        self.kind = kind
        self.attempts = attempts
        self.status_code = status_code
        self.error = _safe_error(error)
        self.retry_after = retry_after


def _parse_retry_after(value: object, now: datetime | None = None) -> float | None:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP-date),
    capped at N8N_RETRY_AFTER_MAX_SECONDS; None when absent or malformed."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]{1,10}", value):
        seconds = float(value)
    else:
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None
        if when is None:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or _now())).total_seconds()
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), settings.N8N_RETRY_AFTER_MAX_SECONDS)


async def _dispatch(event: dict[str, Any], deadline: float | None = None) -> None:
    """POSTs one event with up to N8N_MAX_ATTEMPTS tries, never past
    `deadline` (time.monotonic()). Waits exponential backoff between tries, or
    the server's Retry-After on 429/503 when that fits the remaining time.
    Every try carries the same event_id (body and Idempotency-Key header).
    Raises N8nDeliveryError when it gives up."""
    headers = {"Content-Type": "application/json", "Idempotency-Key": str(event["event_id"])}
    if settings.N8N_WEBHOOK_SECRET:
        headers[settings.N8N_WEBHOOK_HEADER_NAME] = settings.N8N_WEBHOOK_SECRET

    max_attempts = max(1, settings.N8N_MAX_ATTEMPTS)
    status_code: int | None = None
    error = ""
    attempts = 0
    retry_after: float | None = None

    def remaining() -> float:
        return float("inf") if deadline is None else deadline - time.monotonic()

    async with httpx.AsyncClient(timeout=float(settings.N8N_TIMEOUT_SECONDS)) as client:
        for attempt in range(1, max_attempts + 1):
            if remaining() <= 0:
                error = error or "time budget exhausted before sending"
                break
            attempts = attempt
            retry_after = None
            timeout = min(float(settings.N8N_TIMEOUT_SECONDS), remaining())
            try:
                response = await client.post(
                    settings.N8N_WEBHOOK_URL, headers=headers, json=event, timeout=timeout
                )
            except httpx.TransportError as exc:  # timeouts, connect/read errors
                status_code, error = None, _safe_error(f"{type(exc).__name__}: {exc}")
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
                if status_code in _RETRY_AFTER_STATUS:
                    retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                "n8n_webhook_dispatch_failed",
                event_type=event.get("event"),
                event_id=event.get("event_id"),
                attempt=attempt,
                max_attempts=max_attempts,
                error=error,
            )
            if attempt < max_attempts:
                delay = (
                    retry_after
                    if retry_after is not None
                    else settings.N8N_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1)
                )
                if delay >= remaining():
                    break
                await _sleep(delay)
    raise N8nDeliveryError(FAILURE_TRANSIENT, attempts, status_code, error, retry_after)


async def _claim(
    bind: _Bind, *, event_id: str | None = None, exclude: Sequence[str] = ()
) -> tuple[dict[str, Any], str] | None:
    """Leases one PENDING row (a specific one, or the next due one) whose
    lease is free or expired. Short transaction; returns (payload, token)."""
    now = _now()
    stmt = select(N8nOutboxModel).where(
        N8nOutboxModel.status == STATUS_PENDING,
        or_(N8nOutboxModel.lease_until.is_(None), N8nOutboxModel.lease_until < now),
    )
    if event_id is not None:
        stmt = stmt.where(N8nOutboxModel.event_id == event_id)
    else:
        stmt = stmt.where(N8nOutboxModel.next_attempt_at <= now).order_by(
            N8nOutboxModel.next_attempt_at, N8nOutboxModel.created_at
        )
    if exclude:
        stmt = stmt.where(N8nOutboxModel.event_id.not_in(list(exclude)))
    stmt = stmt.limit(1).with_for_update(skip_locked=True)
    async with AsyncSession(bind, expire_on_commit=False) as s:
        row = await s.scalar(stmt)
        if row is None:
            return None
        token = uuid.uuid4().hex
        row.lease_token = token
        row.lease_until = now + timedelta(seconds=settings.N8N_OUTBOX_LEASE_SECONDS)
        payload = dict(row.payload)
        await s.commit()
    return payload, token


def _redispatch_delay(attempts: int, exc: N8nDeliveryError) -> float:
    if exc.retry_after is not None:
        return min(exc.retry_after, settings.N8N_RETRY_AFTER_MAX_SECONDS)
    if exc.attempts == 0:  # never sent (budget ran out first): due again now
        return 0.0
    dispatches = max(1, math.ceil(attempts / max(1, settings.N8N_MAX_ATTEMPTS)))
    return min(_REDISPATCH_BASE_SECONDS * 2 ** (dispatches - 1), _REDISPATCH_MAX_SECONDS)


async def _record_outcome(
    bind: _Bind,
    event_id: str,
    token: str,
    exc: N8nDeliveryError | None,
    *,
    released: bool = False,
) -> str:
    """Writes a dispatch outcome, only if `token` still holds the lease.
    Never raises; returns delivered | pending | permanent | released |
    lease_lost | error."""
    try:
        async with AsyncSession(bind, expire_on_commit=False) as s:
            row = await s.scalar(
                select(N8nOutboxModel)
                .where(N8nOutboxModel.event_id == event_id, N8nOutboxModel.lease_token == token)
                .with_for_update()
            )
            if row is None:
                logger.warning("n8n_outbox_lease_lost", event_id=event_id)
                return "lease_lost"
            now = _now()
            row.lease_token = None
            row.lease_until = None
            if released:
                row.next_attempt_at = now
                outcome = "released"
            elif exc is None:
                row.status = STATUS_DELIVERED
                row.delivered_at = now
                row.last_error = ""
                _redact(row, now)
                outcome = "delivered"
            else:
                row.attempts += exc.attempts
                row.last_status_code = exc.status_code
                row.last_error = exc.error
                if (
                    exc.kind == FAILURE_PERMANENT
                    or row.attempts >= settings.N8N_OUTBOX_MAX_ATTEMPTS
                ):
                    row.status = STATUS_PERMANENT
                    outcome = "permanent"
                else:
                    row.next_attempt_at = now + timedelta(
                        seconds=_redispatch_delay(row.attempts, exc)
                    )
                    outcome = "pending"
            attempts = row.attempts
            await s.commit()
    except Exception as record_exc:
        logger.error(
            "n8n_outbox_outcome_not_recorded",
            event_id=event_id,
            error=_safe_error(f"{type(record_exc).__name__}: {record_exc}")[:300],
        )
        return "error"
    log = logger.warning if outcome in ("pending", "permanent") else logger.info
    log("n8n_outbox_outcome", event_id=event_id, outcome=outcome, attempts=attempts)
    return outcome


async def _process_one(
    bind: _Bind,
    deadline: float,
    *,
    event_id: str | None = None,
    exclude: Sequence[str] = (),
) -> tuple[str, str] | None:
    """Claims, sends and settles one event. Returns (event_id, outcome), or
    None when nothing was claimable. The outcome write is shielded from
    cancellation; a cancelled send releases the lease so the event (same
    event_id) is retried promptly. Raises only CancelledError."""
    try:
        claimed = await _claim(bind, event_id=event_id, exclude=exclude)
    except Exception as exc:
        logger.error(
            "n8n_outbox_claim_failed",
            event_id=event_id,
            error=_safe_error(f"{type(exc).__name__}: {exc}")[:300],
        )
        return None
    if claimed is None:
        return None
    payload, token = claimed
    claimed_id = str(payload["event_id"])
    lease_deadline = time.monotonic() + settings.N8N_OUTBOX_LEASE_SECONDS - _LEASE_MARGIN_SECONDS
    failure: N8nDeliveryError | None = None
    try:
        await _dispatch(payload, min(deadline, lease_deadline))
    except N8nDeliveryError as exc:
        failure = exc
    except asyncio.CancelledError:
        await asyncio.shield(_record_outcome(bind, claimed_id, token, None, released=True))
        raise
    except Exception as exc:  # a bug in the send path must not lose the event
        logger.warning(
            "n8n_webhook_unexpected_dispatch_error",
            event_id=claimed_id,
            error=_safe_error(f"{type(exc).__name__}: {exc}")[:300],
        )
        failure = N8nDeliveryError(FAILURE_TRANSIENT, 1, None, f"unexpected: {type(exc).__name__}")
    outcome = await asyncio.shield(_record_outcome(bind, claimed_id, token, failure))
    return claimed_id, outcome


async def sweep_outbox(bind: _Bind, limit: int = 50) -> dict[str, int]:
    """Dispatches up to `limit` due PENDING events (including ones whose
    dispatcher died and whose lease has expired), each at most once per run.
    Safe to run concurrently with flushes, other sweepers and manual runs."""
    counts = {"delivered": 0, "pending": 0, "permanent": 0}
    if not _enabled():
        return counts
    tried: list[str] = []
    for _ in range(limit):
        deadline = time.monotonic() + settings.N8N_OUTBOX_LEASE_SECONDS
        result = await _process_one(bind, deadline, exclude=tried)
        if result is None:
            break
        claimed_id, outcome = result
        tried.append(claimed_id)
        if outcome in counts:
            counts[outcome] += 1
    return counts


async def purge_outbox(
    bind: _Bind,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
    batch_size: int = _PURGE_BATCH,
) -> dict[str, int]:
    """Applies N8N_FAILURE_RETENTION_DAYS, in batches, idempotently.
    - PENDING/PERMANENT rows created before the cutoff: personal fields
      removed and marked EXPIRED (never sent again).
    - DELIVERED/EXPIRED rows last updated before the cutoff: deleted. A row
      expired in this run is therefore deleted one retention period later.
    Leased rows (being dispatched) are skipped. No retention configured =
    nothing is touched."""
    days = settings.N8N_FAILURE_RETENTION_DAYS if retention_days is None else retention_days
    counts = {"expired": 0, "deleted": 0}
    if days is None:
        logger.info("n8n_outbox_purge_skipped", reason="N8N_FAILURE_RETENTION_DAYS not set")
        return counts
    if days < 1:
        raise ValueError("retention_days must be >= 1")
    now = now or _now()
    cutoff = now - timedelta(days=days)
    unleased = or_(N8nOutboxModel.lease_until.is_(None), N8nOutboxModel.lease_until < now)

    while True:
        async with AsyncSession(bind, expire_on_commit=False) as s:
            rows = (
                await s.scalars(
                    select(N8nOutboxModel)
                    .where(
                        N8nOutboxModel.status.in_([STATUS_PENDING, STATUS_PERMANENT]),
                        N8nOutboxModel.created_at < cutoff,
                        unleased,
                    )
                    .order_by(N8nOutboxModel.created_at)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                row.status = STATUS_EXPIRED
                row.lease_token = None
                row.lease_until = None
                _redact(row, now)
            await s.commit()
        counts["expired"] += len(rows)
        if len(rows) < batch_size:
            break

    while True:
        async with AsyncSession(bind, expire_on_commit=False) as s:
            ids = (
                await s.scalars(
                    select(N8nOutboxModel.event_id)
                    .where(
                        N8nOutboxModel.status.in_([STATUS_DELIVERED, STATUS_EXPIRED]),
                        N8nOutboxModel.updated_at < cutoff,
                        unleased,
                    )
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if ids:
                await s.execute(delete(N8nOutboxModel).where(N8nOutboxModel.event_id.in_(ids)))
            await s.commit()
        counts["deleted"] += len(ids)
        if len(ids) < batch_size:
            break

    logger.info("n8n_outbox_purged", retention_days=days, **counts)
    return counts


async def notification_status(db: AsyncSession) -> dict[str, int]:
    """Row counts per outbox status - never payloads."""
    rows = (
        await db.execute(
            select(N8nOutboxModel.status, func.count()).group_by(N8nOutboxModel.status)
        )
    ).all()
    status = {"pending": 0, "delivered": 0, "permanent": 0, "expired": 0}
    for name, count in rows:
        key = str(name).lower()
        status[key] = status.get(key, 0) + int(count)
    return status


async def requeue_permanent_event(bind: _Bind, event_id: str) -> tuple[bool, str]:
    """Operator recovery: returns one PERMANENT event to PENDING (after the
    cause - payload, secret, URL - has been fixed) so the normal dispatchers
    send it again with its ORIGINAL event_id. Sends nothing itself.

    Refuses anything not PERMANENT, and any row whose payload was redacted or
    is incomplete (it could no longer reproduce the notification). One short
    transaction holding the row lock, so concurrent calls serialise and only
    the first succeeds. Returns (requeued, message); never logs the payload."""
    async with AsyncSession(bind, expire_on_commit=False) as s:
        row = await s.scalar(
            select(N8nOutboxModel).where(N8nOutboxModel.event_id == event_id).with_for_update()
        )
        if row is None:
            return False, f"event {event_id} not found"
        if row.status != STATUS_PERMANENT:
            return False, f"event {event_id} is {row.status}; only PERMANENT events can be requeued"
        payload = dict(row.payload)
        if row.redacted_at is not None:
            return False, f"event {event_id} was redacted; it can no longer be resent"
        missing = [k for k in REDELIVERY_REQUIRED_FIELDS if not payload.get(k)]
        if missing or payload.get("event_id") != row.event_id:
            return False, f"event {event_id} has an incomplete payload; it cannot be resent"
        row.status = STATUS_PENDING
        row.attempts = 0  # a fresh N8N_OUTBOX_MAX_ATTEMPTS budget
        row.next_attempt_at = _now()
        row.lease_until = None
        row.lease_token = None
        await s.commit()
    logger.warning("n8n_outbox_requeued", event_id=event_id)
    return True, f"event {event_id} requeued as PENDING; the dispatcher will send it"


async def _sweeper_loop(bind: _Bind, interval: float) -> None:
    while True:
        try:
            await sweep_outbox(bind)
            if settings.N8N_FAILURE_RETENTION_DAYS is not None:
                await purge_outbox(bind)
        except Exception as exc:
            logger.error(
                "n8n_outbox_sweep_failed",
                error=_safe_error(f"{type(exc).__name__}: {exc}")[:300],
            )
        await _sleep(interval)


def start_outbox_sweeper() -> asyncio.Task[None] | None:
    """Starts the background sweeper (from the app lifespan). None when n8n is
    disabled or N8N_OUTBOX_SWEEP_SECONDS is 0."""
    if not _enabled() or settings.N8N_OUTBOX_SWEEP_SECONDS <= 0:
        return None
    from app.db.session import engine

    logger.info("n8n_outbox_sweeper_started", interval_seconds=settings.N8N_OUTBOX_SWEEP_SECONDS)
    return asyncio.create_task(_sweeper_loop(engine, settings.N8N_OUTBOX_SWEEP_SECONDS))
