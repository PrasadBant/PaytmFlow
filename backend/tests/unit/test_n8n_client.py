"""Unit tests for the n8n outbound webhook dispatcher (app/integrations/n8n_client.py).

Covers: queue/flush semantics (never notify before commit, never flush
twice), disabled/unconfigured no-op, dispatch failure never raises, header
auth, rejection of an unknown event_type, and the real payload schema
(event/case_id/journey_id/customer_id/customer_email/message/timestamp -
verified directly against the live n8n workflow's own validation node).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.integrations.n8n_client import flush_n8n_events, queue_event


class _FakeSession:
    """Minimal stand-in for AsyncSession's `.info` dict - the only API
    surface n8n_client actually uses."""

    def __init__(self) -> None:
        self.info: dict = {}


def _mock_response(status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def test_queue_event_rejects_unknown_event_type():
    db = _FakeSession()
    with pytest.raises(ValueError):
        queue_event(db, "NOT_A_REAL_EVENT", uuid4(), case_id="case-1", message="hello")


def test_queue_event_rejects_empty_case_id():
    """The real workflow's own "Valid Payload?" node rejects any event
    with an empty case_id (verified live) - this must be caught before
    ever reaching the network, not after a wasted round trip."""
    db = _FakeSession()
    with pytest.raises(ValueError):
        queue_event(db, "REVIEW_REQUIRED", uuid4(), case_id="", message="hello")


@pytest.mark.asyncio
async def test_flush_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "N8N_ENABLED", False)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/x")
    db = _FakeSession()
    queue_event(db, "REVIEW_REQUIRED", uuid4(), case_id="case-1", message="hello")

    with patch(
        "httpx.AsyncClient.post", new=AsyncMock(side_effect=AssertionError("must not call"))
    ):
        await flush_n8n_events(db)


@pytest.mark.asyncio
async def test_flush_is_noop_when_url_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "")
    db = _FakeSession()
    queue_event(db, "REVIEW_REQUIRED", uuid4(), case_id="case-1", message="hello")

    with patch(
        "httpx.AsyncClient.post", new=AsyncMock(side_effect=AssertionError("must not call"))
    ):
        await flush_n8n_events(db)


@pytest.mark.asyncio
async def test_flush_dispatches_queued_events_with_header_auth_and_real_schema(monkeypatch):
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "top-secret")
    db = _FakeSession()
    journey_id = uuid4()
    queue_event(
        db,
        "REVIEW_REQUIRED",
        journey_id,
        case_id="case-abc",
        message="Bank statement credit differs from salary slip",
        customer_id="session-xyz",
    )

    mock_post = AsyncMock(return_value=_mock_response(200))
    with patch("httpx.AsyncClient.post", new=mock_post):
        await flush_n8n_events(db)

    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"][settings.N8N_WEBHOOK_HEADER_NAME] == "top-secret"
    sent_json = kwargs["json"]
    # Real field names verified against the live workflow's "Normalize
    # Event"/"Valid Payload?" nodes - "event" (not "event_type"),
    # "timestamp" (not "occurred_at").
    assert sent_json["event"] == "REVIEW_REQUIRED"
    assert sent_json["journey_id"] == str(journey_id)
    assert sent_json["case_id"] == "case-abc"
    assert sent_json["customer_id"] == "session-xyz"
    assert sent_json["customer_email"] == ""
    assert sent_json["message"] == "Bank statement credit differs from salary slip"
    assert "event_id" in sent_json
    assert "timestamp" in sent_json


@pytest.mark.asyncio
async def test_flush_dispatches_real_customer_email_when_provided(monkeypatch):
    """When a caller looked up a real, customer-supplied email (see
    review_service.resolve_case/request_information), it must reach the
    payload verbatim - not be dropped, and not fall back to "" ."""
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()
    queue_event(
        db,
        "JOURNEY_RESOLVED",
        uuid4(),
        case_id="case-abc",
        message="RESOLVED_NO_ACTION: resolved",
        customer_id="session-xyz",
        customer_email="customer@example.com",
    )

    mock_post = AsyncMock(return_value=_mock_response(200))
    with patch("httpx.AsyncClient.post", new=mock_post):
        await flush_n8n_events(db)

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["customer_email"] == "customer@example.com"


@pytest.mark.asyncio
async def test_flush_only_sends_once_even_if_called_twice(monkeypatch):
    """Duplicate protection: flush POPS the queue, so a second flush call
    (e.g. a bug in a caller) sends nothing."""
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()
    queue_event(db, "ESCALATED", uuid4(), case_id="case-1", message="Escalated for review")

    mock_post = AsyncMock(return_value=_mock_response(200))
    with patch("httpx.AsyncClient.post", new=mock_post):
        await flush_n8n_events(db)
        await flush_n8n_events(db)

    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_flush_never_raises_on_dispatch_failure(monkeypatch):
    """n8n being down must never fail the request that triggered it."""
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()
    queue_event(db, "JOURNEY_RESOLVED", uuid4(), case_id="case-1", message="Resolved")

    import httpx

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("boom"))):
        await flush_n8n_events(db)  # must not raise


@pytest.mark.asyncio
async def test_flush_with_nothing_queued_does_not_call_http(monkeypatch):
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()

    with patch(
        "httpx.AsyncClient.post", new=AsyncMock(side_effect=AssertionError("must not call"))
    ):
        await flush_n8n_events(db)


@pytest.mark.asyncio
async def test_flush_dispatches_journey_completed_with_real_customer_email(monkeypatch):
    """JOURNEY_COMPLETED is a sixth, valid event type - orthogonal to the
    five Review Center lifecycle events - fired when a journey's OWN
    readiness reaches READY (see journey_service.py's apply_action/
    submit_clarification), with or without ever going through review."""
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()
    journey_id = uuid4()
    queue_event(
        db,
        "JOURNEY_COMPLETED",
        journey_id,
        case_id=str(journey_id),
        message="Your LENDING journey is complete and ready.",
        customer_id="session-xyz",
        customer_email="customer@example.com",
    )

    mock_post = AsyncMock(return_value=_mock_response(200))
    with patch("httpx.AsyncClient.post", new=mock_post):
        await flush_n8n_events(db)

    sent_json = mock_post.call_args.kwargs["json"]
    assert sent_json["event"] == "JOURNEY_COMPLETED"
    assert sent_json["journey_id"] == str(journey_id)
    assert sent_json["customer_email"] == "customer@example.com"


@pytest.mark.asyncio
async def test_multiple_queued_events_all_dispatched_in_order(monkeypatch):
    monkeypatch.setattr(settings, "N8N_ENABLED", True)
    monkeypatch.setattr(
        settings, "N8N_WEBHOOK_URL", "https://example.n8n.cloud/webhook/paytmflow-events"
    )
    db = _FakeSession()
    journey_id = uuid4()
    queue_event(
        db, "EVIDENCE_UPLOADED", journey_id, case_id="evidence-1", message="Salary Slip uploaded"
    )
    queue_event(db, "REVIEW_REQUIRED", journey_id, case_id="case-abc", message="Review required")

    mock_post = AsyncMock(return_value=_mock_response(200))
    with patch("httpx.AsyncClient.post", new=mock_post):
        await flush_n8n_events(db)

    assert mock_post.await_count == 2
    sent_events = [call.kwargs["json"]["event"] for call in mock_post.await_args_list]
    assert sent_events == ["EVIDENCE_UPLOADED", "REVIEW_REQUIRED"]
