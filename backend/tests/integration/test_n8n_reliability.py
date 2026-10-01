"""n8n delivery reliability through the outbox: bounded retries on transient
failures, no retry on permanent rejections, one stable event_id across every
try and redispatch, the per-request time budget, and status bookkeeping.
Durability, leases, cancellation and retention: test_n8n_outbox.py."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import N8nOutboxModel
from app.integrations import n8n_client
from app.integrations.n8n_client import (
    STATUS_DELIVERED,
    STATUS_PENDING,
    STATUS_PERMANENT,
    flush_n8n_events,
    notification_status,
    queue_event,
    sweep_outbox,
)

URL = "https://example.n8n.cloud/webhook/paytmflow-events"


def _resp(code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = code
    r.headers = {}
    return r


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", URL)
    monkeypatch.setattr(settings, "N8N_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "N8N_RETRY_BACKOFF_SECONDS", 0.5)
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(n8n_client, "_sleep", fake_sleep)
    return sleeps


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _rows(engine: AsyncEngine) -> list[N8nOutboxModel]:
    async with _factory(engine)() as s:
        return list((await s.scalars(select(N8nOutboxModel))).all())


async def _commit_events(db: AsyncSession, n: int = 1) -> list[str]:
    for _ in range(n):
        queue_event(db, "REVIEW_REQUIRED", uuid4(), case_id="case-1", message="Review required")
    ids = list(db.info[n8n_client._PENDING_KEY][-n:])
    await db.commit()
    return ids


async def _make_due(engine: AsyncEngine) -> None:
    async with _factory(engine)() as s:
        await s.execute(update(N8nOutboxModel).values(next_attempt_at=datetime.now(UTC)))
        await s.commit()


async def test_transient_failures_then_success_retry_with_one_idempotency_key(
    db_session: AsyncSession, db_engine: AsyncEngine, _enabled: list[float]
) -> None:
    [event_id] = await _commit_events(db_session)
    post = AsyncMock(side_effect=[_resp(503), httpx.ConnectError("down"), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
    keys = {c.kwargs["headers"]["Idempotency-Key"] for c in post.await_args_list}
    bodies = {c.kwargs["json"]["event_id"] for c in post.await_args_list}
    assert post.await_count == 3 and keys == bodies == {event_id}
    assert _enabled == [0.5, 1.0]  # exponential backoff
    [row] = await _rows(db_engine)
    assert row.status == STATUS_DELIVERED


async def test_transient_exhaustion_keeps_the_event_pending_for_later(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    [event_id] = await _commit_events(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(503))):
        await flush_n8n_events(db_session)
    [row] = await _rows(db_engine)
    assert (row.event_id, row.status, row.attempts) == (event_id, STATUS_PENDING, 3)
    assert row.last_status_code == 503 and row.last_error == "HTTP 503"
    assert row.lease_token is None
    wait = (row.next_attempt_at - datetime.now(UTC)).total_seconds()
    assert 20 < wait <= 30  # first redispatch backoff


async def test_timeouts_are_transient(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    await _commit_events(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ReadTimeout("slow"))):
        await flush_n8n_events(db_session)
    [row] = await _rows(db_engine)
    assert row.status == STATUS_PENDING and row.last_error.startswith("ReadTimeout")


@pytest.mark.parametrize("code", [400, 401, 404])
async def test_permanent_rejection_is_not_retried(
    db_session: AsyncSession, db_engine: AsyncEngine, code: int
) -> None:
    await _commit_events(db_session)
    post = AsyncMock(return_value=_resp(code))
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
        await _make_due(db_engine)
        await sweep_outbox(db_engine)  # PERMANENT is left for a human
    assert post.await_count == 1
    [row] = await _rows(db_engine)
    assert (row.status, row.attempts, row.last_status_code) == (STATUS_PERMANENT, 1, code)


async def test_secret_is_never_stored(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "super-secret-value")
    await _commit_events(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(401))):
        await flush_n8n_events(db_session)
    [row] = await _rows(db_engine)
    assert "super-secret-value" not in repr(row.payload) + row.last_error


async def test_one_failing_event_does_not_block_the_next(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    first, second = await _commit_events(db_session, 2)
    post = AsyncMock(side_effect=[_resp(400), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
    rows = {r.event_id: r.status for r in await _rows(db_engine)}
    assert rows == {first: STATUS_PERMANENT, second: STATUS_DELIVERED}


async def test_flush_budget_bounds_request_latency_and_defers_the_rest(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_FLUSH_BUDGET_SECONDS", 0.5)
    ids = await _commit_events(db_session, 3)

    async def slow_fail(*_a: object, **_k: object) -> MagicMock:
        await asyncio.sleep(0.6)
        return _resp(503)

    start = asyncio.get_running_loop().time()
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_fail)):
        await flush_n8n_events(db_session)
    assert asyncio.get_running_loop().time() - start < 2.0  # not 3 events x 3 tries x 5 s
    rows = await _rows(db_engine)
    assert {r.event_id for r in rows} == set(ids)
    assert all(r.status == STATUS_PENDING for r in rows)
    assert sum(r.attempts for r in rows) <= 1  # at most the first event was tried


async def test_outcome_write_failure_never_raises_and_the_event_is_recoverable(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    [event_id] = await _commit_events(db_session)
    real_session = n8n_client.AsyncSession
    calls = 0

    def flaky_session(*args: object, **kwargs: object) -> AsyncSession:
        nonlocal calls
        calls += 1
        if calls == 2:  # the claim succeeds, the outcome write cannot connect
            raise RuntimeError("database unavailable")
        return real_session(*args, **kwargs)  # type: ignore[arg-type]

    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(200))),
        patch.object(n8n_client, "AsyncSession", new=flaky_session),
    ):
        await flush_n8n_events(db_session)  # must not raise
    [row] = await _rows(db_engine)
    assert row.status == STATUS_PENDING and row.lease_token is not None
    async with _factory(db_engine)() as s:
        await s.execute(
            update(N8nOutboxModel).values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert post.call_args.kwargs["json"]["event_id"] == event_id


async def test_redispatch_accumulates_attempts_until_the_total_cap(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_OUTBOX_MAX_ATTEMPTS", 7)
    [event_id] = await _commit_events(db_session)
    post = AsyncMock(return_value=_resp(503))
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
        for _ in range(3):
            await _make_due(db_engine)
            await sweep_outbox(db_engine)
    [row] = await _rows(db_engine)
    assert row.event_id == event_id and row.attempts == 9 and row.status == STATUS_PERMANENT
    assert {c.kwargs["json"]["event_id"] for c in post.await_args_list} == {event_id}


async def test_sweep_sends_only_due_pending_events(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    pending, permanent = await _commit_events(db_session, 2)
    with patch(
        "httpx.AsyncClient.post", new=AsyncMock(side_effect=[_resp(503)] * 3 + [_resp(400)])
    ):
        await flush_n8n_events(db_session)
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        assert (await sweep_outbox(db_engine))["delivered"] == 0  # backoff not yet due
        await _make_due(db_engine)
        assert await sweep_outbox(db_engine) == {"delivered": 1, "pending": 0, "permanent": 0}
        assert (await sweep_outbox(db_engine))["delivered"] == 0  # already delivered
    assert [c.kwargs["json"]["event_id"] for c in post.await_args_list] == [pending]
    rows = {r.event_id: r.status for r in await _rows(db_engine)}
    assert rows == {pending: STATUS_DELIVERED, permanent: STATUS_PERMANENT}


async def test_two_simultaneous_sweeps_of_one_event_send_it_once(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    if db_engine.dialect.name != "postgresql":
        pytest.skip("SKIP LOCKED semantics require PostgreSQL")
    [event_id] = await _commit_events(db_session)
    sent: list[str] = []

    async def slow_ok(*_a: object, **kwargs: dict) -> MagicMock:
        sent.append(kwargs["json"]["event_id"])
        await asyncio.sleep(0.1)
        return _resp(200)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_ok)):
        a, b = await asyncio.gather(sweep_outbox(db_engine), sweep_outbox(db_engine))
    assert sent == [event_id]
    assert sorted([a["delivered"], b["delivered"]]) == [0, 1]


async def test_timeout_after_receipt_retries_the_same_event(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    """n8n processed the event but the response was lost; the retry carries the
    identical event_id and Idempotency-Key. Whether n8n then notifies once
    depends on the workflow deduplicating on it (simulated here, NOT verified
    against the live workflow)."""
    [event_id] = await _commit_events(db_session)
    received: list[tuple[str, str]] = []
    notified: set[str] = set()

    async def receiver(*_a: object, **kwargs: dict) -> MagicMock:
        eid = kwargs["json"]["event_id"]
        received.append((eid, kwargs["headers"]["Idempotency-Key"]))
        notified.add(eid)
        if len(received) == 1:
            raise httpx.ReadTimeout("processed, but the response never arrived")
        return _resp(200)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=receiver)):
        await flush_n8n_events(db_session)
    assert received == [(event_id, event_id), (event_id, event_id)]
    assert notified == {event_id}
    [row] = await _rows(db_engine)
    assert row.status == STATUS_DELIVERED


async def test_status_reports_counts_only(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    await _commit_events(db_session, 3)
    post = AsyncMock(side_effect=[_resp(200), _resp(400)] + [_resp(503)] * 3)
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
    async with _factory(db_engine)() as s:
        status = await notification_status(s)
    assert status == {"pending": 1, "delivered": 1, "permanent": 1, "expired": 0}
    assert all(isinstance(v, int) for v in status.values())
