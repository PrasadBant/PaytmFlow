"""Manual / cron fallback for the n8n outbox (the app also sweeps it in the
background every N8N_OUTBOX_SWEEP_SECONDS).

Usage:
  python -m app.integrations.n8n_redeliver                      send due PENDING events
  python -m app.integrations.n8n_redeliver --status             counts per status (outbox and
                                                                receiver receipts), sends nothing
  python -m app.integrations.n8n_redeliver --purge              apply N8N_FAILURE_RETENTION_DAYS
  python -m app.integrations.n8n_redeliver --requeue EVENT_ID   PERMANENT -> PENDING, sends nothing

--requeue is for an event n8n rejected (PERMANENT) once the cause is fixed: it
is sent again by the normal dispatchers, with its original event_id.

receipts_stale_claims in --status counts events the n8n workflow claimed but
never completed: the notification may not have been sent. Check them by hand;
they are never reclaimed automatically (that could notify twice).
"""

import asyncio
import sys

from app.db.session import async_session_factory, engine
from app.integrations.n8n_client import (
    notification_status,
    purge_outbox,
    requeue_permanent_event,
    sweep_outbox,
)
from app.integrations.n8n_receipts import purge_receipts, receipt_status

USAGE = "usage: python -m app.integrations.n8n_redeliver [--status | --purge | --requeue EVENT_ID]"


def _line(title: str, counts: dict[str, int]) -> str:
    return f"{title}: " + " ".join(f"{k}={v}" for k, v in counts.items())


def requeue_target(args: list[str]) -> str | None:
    """The EVENT_ID after --requeue; raises ValueError when it is missing."""
    if "--requeue" not in args:
        return None
    rest = args[args.index("--requeue") + 1 :]
    if not rest or rest[0].startswith("--") or not rest[0].strip():
        raise ValueError(USAGE)
    return rest[0].strip()


async def _main(args: list[str]) -> int:
    try:
        target = requeue_target(args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    try:
        if target is not None:
            ok, message = await requeue_permanent_event(engine, target)
            print(message)
            return 0 if ok else 1
        if "--status" in args:
            async with async_session_factory() as db:
                print(_line("n8n outbox", await notification_status(db)))
                print(_line("n8n receipts", await receipt_status(db)))
        elif "--purge" in args:
            print(_line("n8n outbox purge", await purge_outbox(engine)))
            print(_line("n8n receipts purge", {"deleted": await purge_receipts(engine)}))
        else:
            print(_line("n8n outbox dispatch", await sweep_outbox(engine)))
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
