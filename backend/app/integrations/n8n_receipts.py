"""Receiver-side idempotency for the n8n workflow.

The sender (n8n_client.py) delivers at least once: a timeout, a lost response
or a crash after n8n accepted an event makes it send the same event_id again,
possibly while the first delivery is still running. The workflow therefore
calls these functions over HTTP (app/api/v1/n8n_receipts.py) around every
notification:

    claim(event_id)    -> one atomic INSERT ... ON CONFLICT DO NOTHING RETURNING.
                          Exactly one caller per event_id gets claimed=True; it
                          alone may notify. Everyone else answers "duplicate".
    complete(event_id) -> CLAIMED -> SENT after the notification went out.
    release(event_id)  -> deletes a CLAIMED row after a CLEAN send failure, so
                          the sender's retry may claim and send again.

Chosen semantics: never notify twice for one event_id. The cost is one
narrow window - the winner dies after claiming and before its send fails
cleanly - in which the claim stays CLAIMED and the notification is not sent
(retries are told "duplicate"). Stale CLAIMED rows are reported by
`notification_status` / `--status`, never reclaimed automatically: reclaiming
cannot tell "never sent" from "sent, then crashed" and could notify twice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.config import settings
from app.db.models import N8nReceiptModel

logger = structlog.get_logger()

RECEIPT_CLAIMED = "CLAIMED"
RECEIPT_SENT = "SENT"
# A claim older than this without completion is reported as stale.
STALE_CLAIM_AFTER = timedelta(minutes=10)
_PURGE_BATCH = 500


def _now() -> datetime:
    return datetime.now(UTC)


def _insert(db: AsyncSession):
    dialect = db.get_bind().dialect.name
    return sqlite_insert if dialect == "sqlite" else pg_insert


async def claim(db: AsyncSession, event_id: str, event_type: str = "") -> tuple[bool, str]:
    """Atomically claims event_id. Returns (claimed, status): (True, CLAIMED)
    for the single winner, (False, <existing status>) for everyone else. The
    database's primary key decides the winner; there is no read-then-write."""
    stmt = (
        _insert(db)(N8nReceiptModel)
        .values(
            event_id=event_id, event_type=event_type[:50], status=RECEIPT_CLAIMED, claimed_at=_now()
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(N8nReceiptModel.event_id)
    )
    won = (await db.execute(stmt)).scalar_one_or_none() is not None
    await db.commit()
    if won:
        logger.info("n8n_receipt_claimed", event_id=event_id)
        return True, RECEIPT_CLAIMED
    existing = await db.scalar(
        select(N8nReceiptModel.status).where(N8nReceiptModel.event_id == event_id)
    )
    logger.info("n8n_receipt_duplicate", event_id=event_id, status=existing)
    # existing is None only if the row was released between the two statements;
    # the caller still lost this round and the sender will retry.
    return False, existing or RECEIPT_CLAIMED


async def complete(db: AsyncSession, event_id: str) -> str | None:
    """Marks a claim SENT (idempotent). Returns the resulting status, or None
    if there is no claim for event_id."""
    await db.execute(
        update(N8nReceiptModel)
        .where(N8nReceiptModel.event_id == event_id, N8nReceiptModel.status == RECEIPT_CLAIMED)
        .values(status=RECEIPT_SENT, completed_at=_now())
    )
    await db.commit()
    status = await db.scalar(
        select(N8nReceiptModel.status).where(N8nReceiptModel.event_id == event_id)
    )
    if status is not None:
        logger.info("n8n_receipt_completed", event_id=event_id)
    return status


async def release(db: AsyncSession, event_id: str) -> bool:
    """Deletes a CLAIMED row after a clean send failure so a retry may send.
    A SENT row is never released (that could notify twice). Returns whether
    a claim was released."""
    result = await db.execute(
        delete(N8nReceiptModel).where(
            N8nReceiptModel.event_id == event_id, N8nReceiptModel.status == RECEIPT_CLAIMED
        )
    )
    await db.commit()
    released = (getattr(result, "rowcount", 0) or 0) > 0
    if released:
        logger.warning("n8n_receipt_released", event_id=event_id)
    return released


async def receipt_status(db: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Counts only: claimed, sent, and stale claims (CLAIMED longer than
    STALE_CLAIM_AFTER - possibly unsent notifications a human should check)."""
    now = now or _now()
    rows = (
        await db.execute(
            select(N8nReceiptModel.status, func.count()).group_by(N8nReceiptModel.status)
        )
    ).all()
    counts = {"receipts_claimed": 0, "receipts_sent": 0}
    for name, count in rows:
        counts[f"receipts_{str(name).lower()}"] = int(count)
    counts["receipts_stale_claims"] = int(
        await db.scalar(
            select(func.count()).where(
                N8nReceiptModel.status == RECEIPT_CLAIMED,
                N8nReceiptModel.claimed_at < now - STALE_CLAIM_AFTER,
            )
        )
        or 0
    )
    return counts


async def purge_receipts(
    bind: AsyncEngine | AsyncConnection,
    *,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    """Deletes receipts claimed before the N8N_FAILURE_RETENTION_DAYS cutoff, in
    batches. Safe: by then the outbox has expired the event, so the sender
    never retries it again. No retention configured = nothing is deleted."""
    days = settings.N8N_FAILURE_RETENTION_DAYS if retention_days is None else retention_days
    if days is None:
        return 0
    if days < 1:
        raise ValueError("retention_days must be >= 1")
    cutoff = (now or _now()) - timedelta(days=days)
    deleted = 0
    while True:
        async with AsyncSession(bind, expire_on_commit=False) as s:
            ids = (
                await s.scalars(
                    select(N8nReceiptModel.event_id)
                    .where(N8nReceiptModel.claimed_at < cutoff)
                    .limit(_PURGE_BATCH)
                )
            ).all()
            if ids:
                await s.execute(delete(N8nReceiptModel).where(N8nReceiptModel.event_id.in_(ids)))
            await s.commit()
        deleted += len(ids)
        if len(ids) < _PURGE_BATCH:
            break
    if deleted:
        logger.info("n8n_receipts_purged", retention_days=days, deleted=deleted)
    return deleted
