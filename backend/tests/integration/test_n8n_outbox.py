"""The n8n transactional outbox against a real database: an event commits or
rolls back with the business write, leases keep two dispatchers off one row,
cancellation and crashes never lose a committed event (it is re-sent with the
same event_id), Retry-After is bounded, and personal data / retention follow
the documented lifecycle. No real network: httpx is mocked throughout."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import N8nOutboxModel, SessionModel
from app.integrations import n8n_client
from app.integrations.n8n_client import (
    PERSONAL_FIELDS,
    REDELIVERY_REQUIRED_FIELDS,
    STATUS_DELIVERED,
    STATUS_EXPIRED,
    STATUS_PENDING,
    STATUS_PERMANENT,
    _claim,
    flush_n8n_events,
    purge_outbox,
    queue_event,
    start_outbox_sweeper,
    sweep_outbox,
)

URL = "https://example.n8n.cloud/webhook/paytmflow-events"
EMAIL = "person@example.com"


class _ProcessDied(BaseException):
    """Stands in for the process being killed: not an Exception, not a
    cancellation, so nothing in the dispatcher can catch and settle it."""


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", URL)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "N8N_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "N8N_RETRY_BACKOFF_SECONDS", 0.5)
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(n8n_client, "_sleep", fake_sleep)
    return sleeps


def _resp(code: int, retry_after: str | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = code
    r.headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return r


def _factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _rows(engine: AsyncEngine) -> list[N8nOutboxModel]:
    async with _factory(engine)() as s:
        return list((await s.scalars(select(N8nOutboxModel))).all())


async def _row(engine: AsyncEngine, event_id: str) -> N8nOutboxModel:
    async with _factory(engine)() as s:
        row = await s.get(N8nOutboxModel, event_id)
        assert row is not None
        return row


async def _queue_committed(
    engine: AsyncEngine, event_type: str = "JOURNEY_RESOLVED", **kwargs: str
) -> str:
    """Queues one event in its own committed transaction; returns its id."""
    async with _factory(engine)() as s:
        queue_event(
            s,
            event_type,
            uuid4(),
            case_id=kwargs.get("case_id", "case-1"),
            message=kwargs.get("message", "Resolved: documents verified"),
            customer_id=kwargs.get("customer_id", "session-1"),
            customer_email=kwargs.get("customer_email", EMAIL),
        )
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        await s.commit()
    return event_id


async def _expire_lease(engine: AsyncEngine, event_id: str) -> None:
    async with _factory(engine)() as s:
        await s.execute(
            update(N8nOutboxModel)
            .where(N8nOutboxModel.event_id == event_id)
            .values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        await s.commit()


async def _age(engine: AsyncEngine, event_id: str, *, days: float, **values: object) -> None:
    then = datetime.now(UTC) - timedelta(days=days)
    async with _factory(engine)() as s:
        await s.execute(
            update(N8nOutboxModel)
            .where(N8nOutboxModel.event_id == event_id)
            .values(created_at=then, updated_at=then, **values)
        )
        await s.commit()


def _require_postgres(engine: AsyncEngine) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("row locking (FOR UPDATE SKIP LOCKED) requires PostgreSQL")


# --- B. queue_event() atomicity ------------------------------------------------


async def test_business_commit_makes_the_outbox_event_durable(db_engine: AsyncEngine) -> None:
    sid = uuid4()
    async with _factory(db_engine)() as s:
        s.add(SessionModel(id=sid, expires_at=datetime.now(UTC) + timedelta(days=1)))
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        assert await _rows(db_engine) == []  # nothing visible before the commit
        await s.commit()
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING and row.attempts == 0
    async with _factory(db_engine)() as s:
        assert await s.get(SessionModel, sid) is not None


async def test_business_rollback_leaves_no_outbox_event(db_engine: AsyncEngine) -> None:
    sid = uuid4()
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        s.add(SessionModel(id=sid, expires_at=datetime.now(UTC) + timedelta(days=1)))
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        await s.flush()  # the INSERT has reached the database inside the transaction
        await s.rollback()
        n8n_client.discard_n8n_events(s)
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    assert await _rows(db_engine) == []
    assert post.await_count == 0
    async with _factory(db_engine)() as s:
        assert await s.get(SessionModel, sid) is None


async def test_failed_business_commit_leaves_no_outbox_event(db_engine: AsyncEngine) -> None:
    sid = uuid4()
    async with _factory(db_engine)() as s:
        s.add(SessionModel(id=sid, expires_at=datetime.now(UTC) + timedelta(days=1)))
        await s.commit()
    async with _factory(db_engine)() as s:
        s.add(SessionModel(id=sid, expires_at=datetime.now(UTC) + timedelta(days=1)))  # dup PK
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        with pytest.raises(IntegrityError):
            await s.commit()
        await s.rollback()
    assert await _rows(db_engine) == []


async def test_event_id_is_the_row_key_body_id_and_idempotency_key(db_engine: AsyncEngine) -> None:
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(s, "REVIEW_REQUIRED", uuid4(), case_id="case-1", message="Review")
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    [row] = await _rows(db_engine)
    assert post.call_args.kwargs["json"]["event_id"] == row.event_id
    assert post.call_args.kwargs["headers"]["Idempotency-Key"] == row.event_id
    assert row.status == STATUS_DELIVERED


async def test_flush_only_sends_once_even_if_called_twice(db_engine: AsyncEngine) -> None:
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated for review")
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
            await flush_n8n_events(s)
    assert post.await_count == 1


async def test_disabled_n8n_stores_nothing(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_ENABLED", False)
    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        await s.commit()
    assert await _rows(db_engine) == []


async def test_a_real_api_flow_commits_its_event_and_delivers_it(
    client: httpx.AsyncClient, db_engine: AsyncEngine, session_headers: dict
) -> None:
    dispatched: list[dict] = []

    async def record(event: dict, deadline: float | None = None) -> None:
        dispatched.append(event)

    with patch.object(n8n_client, "_dispatch", new=record):
        r = await client.post(
            "/api/v1/journeys",
            json={
                "journey_type": "LENDING",
                "goal": {"loan_amount": 200000, "loan_purpose": "EDUCATION", "tenure_months": 24},
            },
            headers=session_headers,
        )
        journey = r.json()
        r = await client.post(
            f"/api/v1/journeys/{journey['journey_id']}/actions",
            json={
                "action_id": "UPLOAD_INCOME_PROOF",
                "expected_snapshot_id": journey["snapshot_id"],
                "idempotency_key": str(uuid4()),
                "input": {"monthly_income": 30000, "ambiguity_id": "INCOME_MISMATCH"},
            },
            headers=session_headers,
        )
        assert r.status_code == 200, r.text
    rows = {row.event_id: row for row in await _rows(db_engine)}
    assert dispatched and {e["event_id"] for e in dispatched} == set(rows)
    assert all(row.status == STATUS_DELIVERED for row in rows.values())


# --- ported from the unit suite: payload schema and dispatch -------------------


async def test_flush_dispatches_with_header_auth_and_real_schema(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "top-secret")
    journey_id = uuid4()
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(
            s,
            "REVIEW_REQUIRED",
            journey_id,
            case_id="case-abc",
            message="Bank statement credit differs from salary slip",
            customer_id="session-xyz",
        )
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    post.assert_awaited_once()
    kwargs = post.call_args.kwargs
    assert kwargs["headers"][settings.N8N_WEBHOOK_HEADER_NAME] == "top-secret"
    sent = kwargs["json"]
    assert sent["event"] == "REVIEW_REQUIRED"
    assert sent["journey_id"] == str(journey_id)
    assert sent["case_id"] == "case-abc"
    assert sent["customer_id"] == "session-xyz"
    assert sent["customer_email"] == ""
    assert sent["message"] == "Bank statement credit differs from salary slip"
    assert "event_id" in sent and "timestamp" in sent


@pytest.mark.parametrize("event_type", ["JOURNEY_RESOLVED", "JOURNEY_COMPLETED"])
async def test_flush_sends_the_real_customer_email(db_engine: AsyncEngine, event_type: str) -> None:
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(
            s,
            event_type,
            uuid4(),
            case_id="case-abc",
            message="done",
            customer_id="session-xyz",
            customer_email="customer@example.com",
        )
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    assert post.call_args.kwargs["json"]["event"] == event_type
    assert post.call_args.kwargs["json"]["customer_email"] == "customer@example.com"


async def test_flush_never_raises_and_keeps_the_event(db_engine: AsyncEngine) -> None:
    async with _factory(db_engine)() as s:
        queue_event(s, "JOURNEY_RESOLVED", uuid4(), case_id="case-1", message="Resolved")
        await s.commit()
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("x"))):
            await flush_n8n_events(s)  # must not raise
    [row] = await _rows(db_engine)
    assert row.status == STATUS_PENDING and row.payload["message"] == "Resolved"


async def test_multiple_queued_events_all_dispatched_in_order(db_engine: AsyncEngine) -> None:
    journey_id = uuid4()
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(
            s, "EVIDENCE_UPLOADED", journey_id, case_id="evidence-1", message="Salary Slip uploaded"
        )
        queue_event(s, "REVIEW_REQUIRED", journey_id, case_id="case-abc", message="Review")
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    assert [c.kwargs["json"]["event"] for c in post.await_args_list] == [
        "EVIDENCE_UPLOADED",
        "REVIEW_REQUIRED",
    ]


# --- C. leasing ------------------------------------------------------------------


async def test_outcome_with_a_stale_lease_token_is_ignored(db_engine: AsyncEngine) -> None:
    event_id = await _queue_committed(db_engine)
    claimed = await _claim(db_engine, event_id=event_id)
    assert claimed is not None
    outcome = await n8n_client._record_outcome(db_engine, event_id, "not-the-token", None)
    assert outcome == "lease_lost"
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING and row.lease_token == claimed[1]


async def test_a_leased_row_is_not_claimed_again_until_the_lease_expires(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _queue_committed(db_engine)
    assert await _claim(db_engine, event_id=event_id) is not None
    assert await _claim(db_engine, event_id=event_id) is None
    assert await _claim(db_engine) is None
    await _expire_lease(db_engine, event_id)
    again = await _claim(db_engine)
    assert again is not None and again[0]["event_id"] == event_id


async def test_concurrent_sweepers_send_each_event_once(db_engine: AsyncEngine) -> None:
    _require_postgres(db_engine)
    ids = [await _queue_committed(db_engine) for _ in range(8)]
    sent: list[str] = []

    async def slow_ok(*_a: object, **kwargs: dict) -> MagicMock:
        sent.append(kwargs["json"]["event_id"])
        await asyncio.sleep(0.02)
        return _resp(200)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_ok)):
        a, b, c = await asyncio.gather(
            sweep_outbox(db_engine), sweep_outbox(db_engine), sweep_outbox(db_engine)
        )
    assert sorted(sent) == sorted(ids)
    assert a["delivered"] + b["delivered"] + c["delivered"] == 8
    assert all(r.status == STATUS_DELIVERED for r in await _rows(db_engine))


async def test_request_flush_and_sweeper_racing_for_one_event_send_it_once(
    db_engine: AsyncEngine,
) -> None:
    _require_postgres(db_engine)
    sent: list[str] = []

    async def slow_ok(*_a: object, **kwargs: dict) -> MagicMock:
        sent.append(kwargs["json"]["event_id"])
        await asyncio.sleep(0.05)
        return _resp(200)

    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        await s.commit()
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_ok)):
            await asyncio.gather(flush_n8n_events(s), sweep_outbox(db_engine))
    assert len(sent) == 1
    [row] = await _rows(db_engine)
    assert row.status == STATUS_DELIVERED


# --- D. cancellation and crashes ----------------------------------------------------


async def test_cancellation_before_the_http_call_keeps_the_event(db_engine: AsyncEngine) -> None:
    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        await s.commit()

        async def cancelled_before_send(*_a: object, **_k: object) -> None:
            raise asyncio.CancelledError

        with patch.object(n8n_client, "_dispatch", new=cancelled_before_send):
            with pytest.raises(asyncio.CancelledError):
                await flush_n8n_events(s)
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING and row.lease_token is None and row.attempts == 0
    with patch("httpx.AsyncClient.post", new=post):
        assert (await sweep_outbox(db_engine))["delivered"] == 1
    assert post.call_args.kwargs["json"]["event_id"] == event_id


async def test_cancellation_during_the_http_call_keeps_the_event(db_engine: AsyncEngine) -> None:
    entered = asyncio.Event()

    async def hang(*_a: object, **_k: object) -> MagicMock:
        entered.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        await s.commit()
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=hang)):
            task = asyncio.create_task(flush_n8n_events(s))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING and row.lease_token is None
    assert row.payload["customer_email"] == "" and row.payload["message"] == "Escalated"

    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert post.call_args.kwargs["json"]["event_id"] == event_id
    assert (await _row(db_engine, event_id)).status == STATUS_DELIVERED


async def test_cancellation_after_remote_success_still_records_delivery(
    db_engine: AsyncEngine,
) -> None:
    real_record = n8n_client._record_outcome
    in_outcome = asyncio.Event()
    release = asyncio.Event()

    async def slow_record(*args: object, **kwargs: object) -> str:
        in_outcome.set()
        await release.wait()
        return await real_record(*args, **kwargs)  # type: ignore[arg-type]

    post = AsyncMock(return_value=_resp(200))
    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        await s.commit()
        with (
            patch("httpx.AsyncClient.post", new=post),
            patch.object(n8n_client, "_record_outcome", new=slow_record),
        ):
            task = asyncio.create_task(flush_n8n_events(s))
            await in_outcome.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()  # the shielded outcome write carries on regardless
            for _ in range(100):
                if (await _row(db_engine, event_id)).status == STATUS_DELIVERED:
                    break
                await asyncio.sleep(0.02)
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_DELIVERED and post.await_count == 1


async def test_crash_after_claim_before_send_is_recovered_with_the_same_event_id(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _queue_committed(db_engine)
    assert await _claim(db_engine) is not None  # the claiming process then dies
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        assert (await sweep_outbox(db_engine))["delivered"] == 0  # lease still held
        await _expire_lease(db_engine, event_id)
        assert (await sweep_outbox(db_engine))["delivered"] == 1
    assert post.call_args.kwargs["headers"]["Idempotency-Key"] == event_id


async def test_crash_during_send_is_recovered_with_the_same_event_id(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _queue_committed(db_engine)
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_ProcessDied())):
        with pytest.raises(_ProcessDied):
            await sweep_outbox(db_engine)
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING and row.lease_token is not None  # orphaned lease
    await _expire_lease(db_engine, event_id)
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        assert (await sweep_outbox(db_engine))["delivered"] == 1
    assert post.call_args.kwargs["json"]["event_id"] == event_id


async def test_crash_after_success_before_commit_resends_the_same_event_id(
    db_engine: AsyncEngine,
) -> None:
    """At-least-once: n8n got it, we never recorded it, so it is sent again with
    the SAME id. Avoiding a second notification is the receiver's job."""
    event_id = await _queue_committed(db_engine)
    post = AsyncMock(return_value=_resp(200))

    async def die(*_a: object, **_k: object) -> str:
        raise _ProcessDied

    with patch("httpx.AsyncClient.post", new=post):
        with patch.object(n8n_client, "_record_outcome", new=die):
            with pytest.raises(_ProcessDied):
                await sweep_outbox(db_engine)
        assert (await _row(db_engine, event_id)).status == STATUS_PENDING
        await _expire_lease(db_engine, event_id)
        await sweep_outbox(db_engine)
    assert [c.kwargs["json"]["event_id"] for c in post.await_args_list] == [event_id, event_id]
    assert (await _row(db_engine, event_id)).status == STATUS_DELIVERED


async def test_repeated_recovery_converges_to_one_delivered_row(db_engine: AsyncEngine) -> None:
    event_id = await _queue_committed(db_engine)
    for _ in range(3):
        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_ProcessDied())):
            with pytest.raises(_ProcessDied):
                await sweep_outbox(db_engine)
        await _expire_lease(db_engine, event_id)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(200))):
        await sweep_outbox(db_engine)
        assert await sweep_outbox(db_engine) == {"delivered": 0, "pending": 0, "permanent": 0}
    [row] = await _rows(db_engine)
    assert row.event_id == event_id and row.status == STATUS_DELIVERED


# --- F. Retry-After ----------------------------------------------------------------


@pytest.mark.parametrize("header", ["2", "HTTP-DATE"])
async def test_retry_after_within_budget_is_honoured(
    db_engine: AsyncEngine, _enabled: list[float], header: str
) -> None:
    if header == "HTTP-DATE":
        when = datetime.now(UTC) + timedelta(seconds=3)
        header = when.strftime("%a, %d %b %Y %H:%M:%S GMT")
    event_id = await _queue_committed(db_engine)
    post = AsyncMock(side_effect=[_resp(429, header), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert len(_enabled) == 1 and 1.0 <= _enabled[0] <= 3.0
    assert {c.kwargs["json"]["event_id"] for c in post.await_args_list} == {event_id}
    assert (await _row(db_engine, event_id)).status == STATUS_DELIVERED


async def test_malformed_retry_after_falls_back_to_backoff(
    db_engine: AsyncEngine, _enabled: list[float]
) -> None:
    await _queue_committed(db_engine)
    post = AsyncMock(side_effect=[_resp(503, "soon-ish"), _resp(200)])
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert _enabled == [0.5]


async def test_retry_after_beyond_the_budget_defers_without_waiting(
    db_engine: AsyncEngine, _enabled: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_RETRY_AFTER_MAX_SECONDS", 600.0)
    post = AsyncMock(return_value=_resp(429, "86400"))
    async with _factory(db_engine)() as s:
        queue_event(s, "ESCALATED", uuid4(), case_id="case-1", message="Escalated")
        event_id = s.info[n8n_client._PENDING_KEY][-1]
        await s.commit()
        with patch("httpx.AsyncClient.post", new=post):
            await flush_n8n_events(s)
    assert post.await_count == 1 and _enabled == []  # no in-request wait at all
    row = await _row(db_engine, event_id)
    assert row.status == STATUS_PENDING
    wait = (row.next_attempt_at - datetime.now(UTC)).total_seconds()
    assert 590 <= wait <= 600  # bounded by N8N_RETRY_AFTER_MAX_SECONDS, not 1 day


# --- G. data minimisation ------------------------------------------------------------


async def test_pending_rows_keep_the_full_payload_and_redelivery_reproduces_it(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _queue_committed(
        db_engine, customer_email=EMAIL, message="RESOLVED: documents verified"
    )
    original = dict((await _row(db_engine, event_id)).payload)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(503))):
        await sweep_outbox(db_engine)
    assert (await _row(db_engine, event_id)).payload == original  # still complete
    await _age(db_engine, event_id, days=0, next_attempt_at=datetime.now(UTC))
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert post.call_args.kwargs["json"] == original


async def test_delivered_rows_keep_only_the_redelivery_contract(db_engine: AsyncEngine) -> None:
    event_id = await _queue_committed(db_engine, customer_email=EMAIL)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=_resp(200))):
        await sweep_outbox(db_engine)
    row = await _row(db_engine, event_id)
    assert set(row.payload) == set(REDELIVERY_REQUIRED_FIELDS)
    assert not set(PERSONAL_FIELDS) & set(row.payload)
    assert row.redacted_at is not None and EMAIL not in str(row.payload)


async def test_stored_error_text_has_no_url_or_secret(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "s3cr3t-value")
    event_id = await _queue_committed(db_engine)
    err = httpx.ConnectError(f"cannot reach {URL} using s3cr3t-value")
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=err)):
        await sweep_outbox(db_engine)
    row = await _row(db_engine, event_id)
    assert "example.n8n.cloud" not in row.last_error and "s3cr3t" not in row.last_error
    assert row.last_error.startswith("ConnectError")


# --- H. retention ---------------------------------------------------------------------


async def _delivered(engine: AsyncEngine) -> str:
    event_id = await _queue_committed(engine)
    async with _factory(engine)() as s:
        await s.execute(
            update(N8nOutboxModel)
            .where(N8nOutboxModel.event_id == event_id)
            .values(status=STATUS_DELIVERED, delivered_at=datetime.now(UTC))
        )
        await s.commit()
    return event_id


async def test_retention_lifecycle_for_each_status(db_engine: AsyncEngine) -> None:
    old_delivered = await _delivered(db_engine)
    recent_delivered = await _delivered(db_engine)
    old_pending = await _queue_committed(db_engine)
    recent_pending = await _queue_committed(db_engine)
    old_permanent = await _queue_committed(db_engine)
    await _age(db_engine, old_delivered, days=10)
    await _age(db_engine, old_pending, days=10)
    await _age(db_engine, old_permanent, days=10, status=STATUS_PERMANENT)
    await _age(db_engine, recent_delivered, days=1)

    assert await purge_outbox(db_engine, retention_days=7) == {"expired": 2, "deleted": 1}
    rows = {r.event_id: r for r in await _rows(db_engine)}
    assert old_delivered not in rows
    assert rows[recent_delivered].status == STATUS_DELIVERED
    assert rows[recent_pending].status == STATUS_PENDING
    assert rows[recent_pending].payload["customer_email"] == EMAIL
    for eid in (old_pending, old_permanent):
        assert rows[eid].status == STATUS_EXPIRED and rows[eid].redacted_at is not None
        assert not set(PERSONAL_FIELDS) & set(rows[eid].payload)

    # Idempotent; EXPIRED rows are never sent, and go one retention period later.
    assert await purge_outbox(db_engine, retention_days=7) == {"expired": 0, "deleted": 0}
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        await sweep_outbox(db_engine)
    assert {c.kwargs["json"]["event_id"] for c in post.await_args_list} == {recent_pending}
    later = datetime.now(UTC) + timedelta(days=8)
    assert (await purge_outbox(db_engine, retention_days=7, now=later))["deleted"] == 4


async def test_retention_cutoff_is_exclusive_and_in_utc(db_engine: AsyncEngine) -> None:
    now = datetime(2026, 10, 2, 0, 0, 0, tzinfo=UTC)
    at_cutoff = await _delivered(db_engine)
    just_past = await _delivered(db_engine)
    async with _factory(db_engine)() as s:
        for eid, ts in (
            (at_cutoff, now - timedelta(days=7)),
            (just_past, now - timedelta(days=7, seconds=1)),
        ):
            await s.execute(
                update(N8nOutboxModel)
                .where(N8nOutboxModel.event_id == eid)
                .values(created_at=ts, updated_at=ts)
            )
        await s.commit()
    # Same instant expressed in another zone: must behave identically.
    ist = now.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert (await purge_outbox(db_engine, retention_days=7, now=ist))["deleted"] == 1
    assert {r.event_id for r in await _rows(db_engine)} == {at_cutoff}


async def test_purge_works_in_bounded_batches(db_engine: AsyncEngine) -> None:
    ids = [await _delivered(db_engine) for _ in range(5)]
    for eid in ids:
        await _age(db_engine, eid, days=30)
    assert await purge_outbox(db_engine, retention_days=7, batch_size=2) == {
        "expired": 0,
        "deleted": 5,
    }
    assert await _rows(db_engine) == []


async def test_purge_never_touches_a_row_being_dispatched(db_engine: AsyncEngine) -> None:
    _require_postgres(db_engine)
    event_id = await _queue_committed(db_engine)
    await _age(db_engine, event_id, days=30)
    in_send = asyncio.Event()
    finish = asyncio.Event()

    async def slow_ok(*_a: object, **_k: object) -> MagicMock:
        in_send.set()
        await finish.wait()
        return _resp(200)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=slow_ok)):
        sweep = asyncio.create_task(sweep_outbox(db_engine))
        await in_send.wait()
        assert await purge_outbox(db_engine, retention_days=7) == {"expired": 0, "deleted": 0}
        finish.set()
        assert (await sweep)["delivered"] == 1
    assert (await _row(db_engine, event_id)).status == STATUS_DELIVERED


async def test_purge_without_retention_configured_changes_nothing(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "N8N_FAILURE_RETENTION_DAYS", None)
    event_id = await _delivered(db_engine)
    await _age(db_engine, event_id, days=3650)
    assert await purge_outbox(db_engine) == {"expired": 0, "deleted": 0}
    assert len(await _rows(db_engine)) == 1
    with pytest.raises(ValueError):
        await purge_outbox(db_engine, retention_days=0)


# --- E. sweeper ------------------------------------------------------------------------


async def test_sweeper_is_off_when_disabled_or_interval_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "N8N_OUTBOX_SWEEP_SECONDS", 0.0)
    assert start_outbox_sweeper() is None
    monkeypatch.setattr(settings, "N8N_OUTBOX_SWEEP_SECONDS", 30.0)
    monkeypatch.setattr(settings, "N8N_ENABLED", False)
    assert start_outbox_sweeper() is None


async def test_sweeper_loop_survives_errors_and_stops_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "N8N_OUTBOX_SWEEP_SECONDS", 30.0)
    monkeypatch.setattr(settings, "N8N_FAILURE_RETENTION_DAYS", 7)
    calls: list[str] = []

    async def failing_sweep(*_a: object, **_k: object) -> dict[str, int]:
        calls.append("sweep")
        raise RuntimeError("database unavailable")

    async def purge(*_a: object, **_k: object) -> dict[str, int]:
        calls.append("purge")
        return {"expired": 0, "deleted": 0}

    ticks = 0

    async def tick(_delay: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= 3:
            await asyncio.Event().wait()  # park until cancelled

    monkeypatch.setattr(n8n_client, "sweep_outbox", failing_sweep)
    monkeypatch.setattr(n8n_client, "purge_outbox", purge)
    monkeypatch.setattr(n8n_client, "_sleep", tick)
    task = start_outbox_sweeper()
    assert task is not None
    for _ in range(100):
        if ticks >= 3:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls.count("sweep") == 3  # kept going after each failure


# --- operator recovery: --requeue -------------------------------------------------


async def _permanent(engine: AsyncEngine, **values: object) -> str:
    event_id = await _queue_committed(engine, customer_email=EMAIL)
    async with _factory(engine)() as s:
        await s.execute(
            update(N8nOutboxModel)
            .where(N8nOutboxModel.event_id == event_id)
            .values(
                status=STATUS_PERMANENT,
                attempts=30,
                last_status_code=400,
                last_error="HTTP 400",
                next_attempt_at=datetime.now(UTC) + timedelta(days=1),
                **values,
            )
        )
        await s.commit()
    return event_id


async def test_requeue_returns_a_permanent_event_to_pending_with_its_event_id(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _permanent(
        db_engine,
        lease_until=datetime.now(UTC) + timedelta(minutes=5),
        lease_token="stale-token",
    )
    original = dict((await _row(db_engine, event_id)).payload)
    post = AsyncMock(return_value=_resp(200))
    with patch("httpx.AsyncClient.post", new=post):
        ok, message = await n8n_client.requeue_permanent_event(db_engine, event_id)
        assert post.await_count == 0  # requeue itself never sends
    assert ok and "requeued" in message and EMAIL not in message
    row = await _row(db_engine, event_id)
    assert row.event_id == event_id and row.payload == original
    assert (row.status, row.attempts) == (STATUS_PENDING, 0)
    assert row.lease_until is None and row.lease_token is None
    assert row.next_attempt_at <= datetime.now(UTC)
    assert (row.last_status_code, row.last_error) == (400, "HTTP 400")  # kept for diagnosis

    # The normal dispatcher then sends it, with the original id.
    with patch("httpx.AsyncClient.post", new=post):
        assert (await sweep_outbox(db_engine))["delivered"] == 1
    assert post.call_args.kwargs["json"] == original
    assert post.call_args.kwargs["headers"]["Idempotency-Key"] == event_id


@pytest.mark.parametrize("status", [STATUS_DELIVERED, STATUS_PENDING, STATUS_EXPIRED])
async def test_requeue_refuses_anything_not_permanent(db_engine: AsyncEngine, status: str) -> None:
    event_id = await _queue_committed(db_engine)
    async with _factory(db_engine)() as s:
        await s.execute(
            update(N8nOutboxModel).where(N8nOutboxModel.event_id == event_id).values(status=status)
        )
        await s.commit()
    before = await _row(db_engine, event_id)
    ok, message = await n8n_client.requeue_permanent_event(db_engine, event_id)
    assert not ok and status in message
    after = await _row(db_engine, event_id)
    assert (after.status, after.next_attempt_at, after.attempts) == (
        before.status,
        before.next_attempt_at,
        before.attempts,
    )


async def test_requeue_refuses_a_redacted_permanent_event(db_engine: AsyncEngine) -> None:
    event_id = await _permanent(db_engine, redacted_at=datetime.now(UTC))
    ok, message = await n8n_client.requeue_permanent_event(db_engine, event_id)
    assert not ok and "redacted" in message
    assert (await _row(db_engine, event_id)).status == STATUS_PERMANENT


async def test_requeue_refuses_an_incomplete_payload_and_unknown_ids(
    db_engine: AsyncEngine,
) -> None:
    event_id = await _permanent(db_engine, payload={"event_id": "x", "event": "ESCALATED"})
    ok, message = await n8n_client.requeue_permanent_event(db_engine, event_id)
    assert not ok and "incomplete" in message
    ok, message = await n8n_client.requeue_permanent_event(db_engine, str(uuid4()))
    assert not ok and "not found" in message


async def test_concurrent_requeues_of_one_event_succeed_once(db_engine: AsyncEngine) -> None:
    _require_postgres(db_engine)
    event_id = await _permanent(db_engine)
    results = await asyncio.gather(
        *(n8n_client.requeue_permanent_event(db_engine, event_id) for _ in range(4))
    )
    assert sorted(ok for ok, _ in results) == [False, False, False, True]
    assert all("PENDING" in message for ok, message in results if not ok)
    rows = await _rows(db_engine)
    assert [(r.event_id, r.status) for r in rows] == [(event_id, STATUS_PENDING)]


def test_requeue_command_requires_an_event_id() -> None:
    from app.integrations.n8n_redeliver import requeue_target

    assert requeue_target(["--status"]) is None
    assert requeue_target(["--requeue", " abc "]) == "abc"
    for bad in (["--requeue"], ["--requeue", "--status"], ["--requeue", " "]):
        with pytest.raises(ValueError):
            requeue_target(bad)
