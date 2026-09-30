"""n8n delivery reliability: bounded retries on transient failures, no retry
on permanent rejections, a stable idempotency key across attempts, durable
failure records, and redelivery."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import NotificationFailureModel, SessionModel
from app.integrations import n8n_client
from app.integrations.n8n_client import (
    FAILURE_PERMANENT,
    FAILURE_TRANSIENT,
    flush_n8n_events,
    queue_event,
    redeliver_failed_events,
)

URL = "https://example.n8n.cloud/webhook/paytmflow-events"


def _resp(code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = code
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

    monkeypatch.setattr(n8n_client, "asyncio", SimpleNamespace(sleep=fake_sleep))
    return sleeps


async def _failures(engine: AsyncEngine) -> list[NotificationFailureModel]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        return list((await s.scalars(select(NotificationFailureModel))).all())


def _queue(db: AsyncSession) -> str:
    queue_event(db, "REVIEW_REQUIRED", uuid4(), case_id="case-1", message="Review required")
    return db.info[n8n_client._PENDING_KEY][-1]["event_id"]


async def test_transient_failures_then_success_retries_with_same_idempotency_key(
    db_session: AsyncSession, db_engine: AsyncEngine, _enabled: list[float]
) -> None:
    event_id = _queue(db_session)
    post = AsyncMock(side_effect=[httpx.ConnectError("down"), _resp(503), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)

    assert post.await_count == 3
    keys = {c.kwargs["headers"]["Idempotency-Key"] for c in post.await_args_list}
    ids = {c.kwargs["json"]["event_id"] for c in post.await_args_list}
    assert keys == ids == {event_id}
    assert _enabled == [0.5, 1.0]  # exponential backoff between the 3 tries
    assert await _failures(db_engine) == []


async def test_transient_exhausted_is_recorded_durably(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    event_id = _queue(db_session)
    post = AsyncMock(return_value=_resp(503))
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)  # must not raise

    assert post.await_count == 3
    [row] = await _failures(db_engine)
    assert row.event_id == event_id
    assert row.failure_kind == FAILURE_TRANSIENT
    assert row.attempts == 3
    assert row.last_status_code == 503
    assert row.payload["event"] == "REVIEW_REQUIRED"
    assert row.delivered_at is None


async def test_timeouts_are_transient(db_session: AsyncSession, db_engine: AsyncEngine) -> None:
    _queue(db_session)
    post = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)

    assert post.await_count == 3
    [row] = await _failures(db_engine)
    assert row.failure_kind == FAILURE_TRANSIENT
    assert row.last_status_code is None
    assert "ReadTimeout" in row.last_error


@pytest.mark.parametrize("code", [400, 401, 404])
async def test_permanent_rejection_is_not_retried(
    db_session: AsyncSession, db_engine: AsyncEngine, code: int
) -> None:
    _queue(db_session)
    post = AsyncMock(return_value=_resp(code))
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)

    assert post.await_count == 1
    [row] = await _failures(db_engine)
    assert row.failure_kind == FAILURE_PERMANENT
    assert row.attempts == 1
    assert row.last_status_code == code


async def test_secret_never_stored_in_failure_record(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "very-secret-header-value")
    _queue(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(500))):
        await flush_n8n_events(db_session)
    [row] = await _failures(db_engine)
    assert "very-secret-header-value" not in f"{row.payload} {row.last_error}"


async def test_one_failing_event_does_not_block_the_next(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _queue(db_session)
    second = _queue(db_session)
    post = AsyncMock(side_effect=[_resp(400), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await flush_n8n_events(db_session)
    assert post.await_args_list[1].kwargs["json"]["event_id"] == second
    assert len(await _failures(db_engine)) == 1


async def test_failure_recording_leaves_caller_session_usable(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    owner = SessionModel(
        id=uuid4(), meta={"role": "CUSTOMER"}, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    db_session.add(owner)
    await db_session.commit()
    _queue(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(500))):
        await flush_n8n_events(db_session)
    # Attribute access must not need a reload (which would fail outside a greenlet).
    assert owner.meta == {"role": "CUSTOMER"}
    assert len(await _failures(db_engine)) == 1


async def test_recording_failure_never_raises(db_session: AsyncSession) -> None:
    _queue(db_session)
    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(500))),
        patch.object(n8n_client, "_upsert_failure", new=AsyncMock(side_effect=RuntimeError("db"))),
    ):
        await flush_n8n_events(db_session)


async def test_redelivery_sends_transient_only_and_marks_delivered(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    transient_id = _queue(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(503))):
        await flush_n8n_events(db_session)
    _queue(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(400))):
        await flush_n8n_events(db_session)

    post = AsyncMock(return_value=_resp(200))
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        with patch("httpx.AsyncClient.post", new=post):
            counts = await redeliver_failed_events(s)

    assert counts == {"delivered": 1, "failed": 0}
    assert post.await_count == 1
    assert post.call_args.kwargs["json"]["event_id"] == transient_id
    rows = {r.event_id: r for r in await _failures(db_engine)}
    assert rows[transient_id].delivered_at is not None
    assert [r for r in rows.values() if r.failure_kind == FAILURE_PERMANENT][0].delivered_at is None

    # Already delivered: a second run sends nothing.
    async with factory() as s:
        with patch("httpx.AsyncClient.post", new=post):
            assert await redeliver_failed_events(s) == {"delivered": 0, "failed": 0}


async def test_failed_redelivery_accumulates_attempts(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    _queue(db_session)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(502))):
        await flush_n8n_events(db_session)
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(502))):
            assert await redeliver_failed_events(s) == {"delivered": 0, "failed": 1}
    [row] = await _failures(db_engine)
    assert row.attempts == 6
    assert row.delivered_at is None


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def monotonic(self) -> float:
        return self.now


async def test_flush_budget_bounds_request_latency_and_defers_the_rest(
    db_session: AsyncSession, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = _Clock()
    monkeypatch.setattr(n8n_client, "time", clock)
    monkeypatch.setattr(settings, "N8N_FLUSH_BUDGET_SECONDS", 4.0)
    monkeypatch.setattr(settings, "N8N_TIMEOUT_SECONDS", 5)
    first = _queue(db_session)
    second = _queue(db_session)
    timeouts: list[float] = []

    async def slow_timeout(*_a, **kwargs):
        timeouts.append(kwargs["timeout"])
        clock.now += kwargs["timeout"]  # the attempt uses its whole timeout
        raise httpx.ReadTimeout("slow")

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_timeout)):
        await flush_n8n_events(db_session)

    # One attempt, capped at the remaining budget (4s, not the 5s timeout).
    assert timeouts == [4.0]
    assert clock.now - 100.0 <= 4.0
    rows = {r.event_id: r for r in await _failures(db_engine)}
    assert rows[first].failure_kind == FAILURE_TRANSIENT and rows[first].attempts == 1
    # The second event never got a turn; it is kept for redelivery, not dropped.
    assert rows[second].failure_kind == FAILURE_TRANSIENT and rows[second].attempts == 0


async def test_concurrent_redelivery_runs_send_each_event_once(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    if db_engine.dialect.name != "postgresql":
        pytest.skip("SKIP LOCKED semantics require PostgreSQL")
    ids = [_queue(db_session) for _ in range(6)]
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(503))):
        await flush_n8n_events(db_session)
    assert len(await _failures(db_engine)) == 6

    sent: list[str] = []

    async def slow_ok(*_a, **kwargs):
        sent.append(kwargs["json"]["event_id"])
        await real_sleep(0.05)  # keep the row lock held while the other run looks
        return _resp(200)

    import asyncio as real_asyncio

    real_sleep = real_asyncio.sleep
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def run() -> dict[str, int]:
        async with factory() as s:
            return await redeliver_failed_events(s)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_ok)):
        a, b = await real_asyncio.gather(run(), run())

    assert sorted(sent) == sorted(ids)  # every event exactly once across both runs
    assert a["delivered"] + b["delivered"] == 6
    assert all(r.delivered_at is not None for r in await _failures(db_engine))
