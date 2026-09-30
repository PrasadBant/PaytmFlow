"""Redelivers n8n events recorded in notification_failures.

Usage: python -m app.integrations.n8n_redeliver  (e.g. as a Render cron job)
"""

import asyncio

from app.db.session import async_session_factory
from app.integrations.n8n_client import redeliver_failed_events


async def _main() -> None:
    async with async_session_factory() as db:
        counts = await redeliver_failed_events(db)
    print(f"n8n redelivery: delivered={counts['delivered']} failed={counts['failed']}")


if __name__ == "__main__":
    asyncio.run(_main())
