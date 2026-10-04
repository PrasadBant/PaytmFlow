"""Receiver-side idempotency for the n8n workflow, against a real database.

The workflow calls claim -> (notify) -> complete, or release after a clean
send failure. These tests drive the HTTP endpoints exactly as the workflow
does, with a counting stand-in for the Slack/email node - nothing is sent."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import N8nReceiptModel
from app.integrations import n8n_receipts

SECRET = "receiver-test-secret-0123456789abcdef"
HEADER = "X-Webhook-Secret"
AUTH = {HEADER: SECRET}


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_HEADER_NAME", HEADER)


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _claim(client: AsyncClient, event_id: str, headers: dict | None = None):
    return await client.post(
        "/api/v1/n8n/receipts/claim",
        json={"event_id": event_id, "event_type": "REVIEW_REQUIRED"},
        headers=AUTH if headers is None else headers,
    )


async def _receive(
    client: AsyncClient,
    event_id: str,
    notify: Callable[[str], Awaitable[None]],
    *,
    complete: bool = True,
) -> str:
    """The workflow's path: claim; only the winner notifies; then complete,
    or release if the notification failed cleanly."""
    r = await _claim(client, event_id)
    assert r.status_code == 200, r.text
    if not r.json()["claimed"]:
        return "duplicate"
    try:
        await notify(event_id)
    except RuntimeError:
        rel = await client.post(f"/api/v1/n8n/receipts/{event_id}/release", headers=AUTH)
        assert rel.status_code == 200
        return "failed"
    if complete:
        done = await client.post(f"/api/v1/n8n/receipts/{event_id}/complete", headers=AUTH)
        assert done.status_code == 200
    return "notified"


def _counter() -> tuple[list[str], Callable[[str], Awaitable[None]]]:
    sent: list[str] = []

    async def notify(event_id: str) -> None:
        await asyncio.sleep(0.01)  # widen any race window
        sent.append(event_id)

    return sent, notify


async def test_first_claim_wins_and_returns_claimed(client: AsyncClient) -> None:
    eid = str(uuid4())
    r = await _claim(client, eid)
    assert r.status_code == 200
    assert r.json() == {"event_id": eid, "claimed": True, "status": "CLAIMED"}


async def test_sequential_duplicate_notifies_once(client: AsyncClient) -> None:
    sent, notify = _counter()
    eid = str(uuid4())
    assert await _receive(client, eid, notify) == "notified"
    assert await _receive(client, eid, notify) == "duplicate"
    assert sent == [eid]
    again = await _claim(client, eid)
    assert again.json() == {"event_id": eid, "claimed": False, "status": "SENT"}


async def test_concurrent_deliveries_of_one_event_notify_once(client: AsyncClient) -> None:
    sent, notify = _counter()
    eid = str(uuid4())
    results = await asyncio.gather(*[_receive(client, eid, notify) for _ in range(12)])
    assert results.count("notified") == 1
    assert results.count("duplicate") == 11
    assert sent == [eid]


async def test_concurrent_claims_have_exactly_one_winner(db_engine: AsyncEngine) -> None:
    """Below the HTTP layer: independent sessions racing on one event_id. On
    PostgreSQL the primary key decides; there is no read-then-write."""
    eid = str(uuid4())

    async def one() -> bool:
        async with _factory(db_engine)() as s:
            claimed, _ = await n8n_receipts.claim(s, eid, "ESCALATED")
            return claimed

    wins = await asyncio.gather(*[one() for _ in range(25)])
    assert wins.count(True) == 1
    async with _factory(db_engine)() as s:
        rows = (
            await s.scalars(select(N8nReceiptModel).where(N8nReceiptModel.event_id == eid))
        ).all()
    assert len(rows) == 1


async def test_different_events_claim_independently(client: AsyncClient) -> None:
    sent, notify = _counter()
    ids = [str(uuid4()) for _ in range(5)]
    results = await asyncio.gather(*[_receive(client, eid, notify) for eid in ids])
    assert results == ["notified"] * 5
    assert sorted(sent) == sorted(ids)


@pytest.mark.parametrize(
    "body", [{}, {"event_id": ""}, {"event_id": "a" * 65}, {"event_id": "has space"}]
)
async def test_missing_or_malformed_event_id_is_rejected(client: AsyncClient, body: dict) -> None:
    r = await client.post("/api/v1/n8n/receipts/claim", json=body, headers=AUTH)
    assert r.status_code in (400, 422)


@pytest.mark.parametrize(
    "headers",
    [{}, {HEADER: "wrong"}, {HEADER: ""}, {"X-Other": SECRET}],
    ids=["none", "wrong", "empty", "other"],
)
async def test_bad_or_missing_secret_is_refused(client: AsyncClient, headers: dict) -> None:
    eid = str(uuid4())
    for r in (
        await _claim(client, eid, headers),
        await client.post(f"/api/v1/n8n/receipts/{eid}/complete", headers=headers),
        await client.post(f"/api/v1/n8n/receipts/{eid}/release", headers=headers),
    ):
        assert r.status_code == 401
    assert SECRET not in r.text


async def test_no_configured_secret_fails_closed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "")
    r = await _claim(client, str(uuid4()), {HEADER: ""})
    assert r.status_code == 401


async def test_retry_after_success_never_notifies_again(client: AsyncClient) -> None:
    sent, notify = _counter()
    eid = str(uuid4())
    await _receive(client, eid, notify)
    for _ in range(3):  # sender retries after a lost response / timeout
        assert await _receive(client, eid, notify) == "duplicate"
    assert sent == [eid]


async def test_notified_but_completion_failed_retry_does_not_notify_again(
    client: AsyncClient,
) -> None:
    """Window B: the notification went out, recording completion failed. The
    claim already exists, so the retry is a duplicate."""
    sent, notify = _counter()
    eid = str(uuid4())
    assert await _receive(client, eid, notify, complete=False) == "notified"
    assert await _receive(client, eid, notify) == "duplicate"
    assert sent == [eid]


async def test_clean_send_failure_releases_so_the_retry_sends(client: AsyncClient) -> None:
    sent: list[str] = []
    calls = {"n": 0}

    async def flaky(event_id: str) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("smtp unavailable")
        sent.append(event_id)

    eid = str(uuid4())
    assert await _receive(client, eid, flaky) == "failed"
    assert await _receive(client, eid, flaky) == "notified"
    assert sent == [eid]


async def test_a_sent_receipt_is_never_released(client: AsyncClient) -> None:
    sent, notify = _counter()
    eid = str(uuid4())
    await _receive(client, eid, notify)
    r = await client.post(f"/api/v1/n8n/receipts/{eid}/release", headers=AUTH)
    assert r.json() == {"event_id": eid, "released": False}
    assert await _receive(client, eid, notify) == "duplicate"
    assert sent == [eid]


async def test_stale_claim_is_reported_and_never_reclaimed(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    """Window C (crash after claiming, before sending): the claim stays, the
    retry is a duplicate (no second notification; this one may be lost), and
    --status reports it for a human."""
    sent, notify = _counter()
    eid = str(uuid4())
    assert (await _claim(client, eid)).json()["claimed"] is True  # winner then "dies"
    async with _factory(db_engine)() as s:
        await s.execute(
            update(N8nReceiptModel)
            .where(N8nReceiptModel.event_id == eid)
            .values(claimed_at=datetime.now(UTC) - timedelta(hours=1))
        )
        await s.commit()
    assert await _receive(client, eid, notify) == "duplicate"
    assert sent == []
    async with _factory(db_engine)() as s:
        counts = await n8n_receipts.receipt_status(s)
    assert counts["receipts_stale_claims"] >= 1
    assert counts["receipts_claimed"] >= 1


async def test_complete_unknown_event_is_404(client: AsyncClient) -> None:
    r = await client.post(f"/api/v1/n8n/receipts/{uuid4()}/complete", headers=AUTH)
    assert r.status_code == 404


async def test_claims_survive_a_restart(client: AsyncClient, db_engine: AsyncEngine) -> None:
    """Dedup state lives in the database, not in process memory: a fresh
    engine (a restarted app) still sees the claim."""
    eid = str(uuid4())
    await _claim(client, eid)
    from sqlalchemy.ext.asyncio import create_async_engine

    fresh = create_async_engine(db_engine.url)
    try:
        async with _factory(fresh)() as s:
            claimed, state = await n8n_receipts.claim(s, eid)
        assert (claimed, state) == (False, "CLAIMED")
    finally:
        await fresh.dispose()


async def test_purge_applies_retention_in_batches(db_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    old, recent = str(uuid4()), str(uuid4())
    async with _factory(db_engine)() as s:
        s.add(N8nReceiptModel(event_id=old, status="SENT", claimed_at=now - timedelta(days=40)))
        s.add(N8nReceiptModel(event_id=recent, status="SENT", claimed_at=now - timedelta(days=5)))
        await s.commit()
    assert await n8n_receipts.purge_receipts(db_engine, retention_days=30, now=now) == 1
    async with _factory(db_engine)() as s:
        left = set((await s.scalars(select(N8nReceiptModel.event_id))).all())
    assert recent in left and old not in left


async def test_purge_without_retention_deletes_nothing(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_FAILURE_RETENTION_DAYS", None)
    async with _factory(db_engine)() as s:
        s.add(
            N8nReceiptModel(
                event_id=str(uuid4()),
                status="SENT",
                claimed_at=datetime.now(UTC) - timedelta(days=400),
            )
        )
        await s.commit()
    assert await n8n_receipts.purge_receipts(db_engine) == 0
