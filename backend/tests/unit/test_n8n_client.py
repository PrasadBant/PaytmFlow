"""Unit tests for the n8n dispatcher (app/integrations/n8n_client.py) that need
no database: event validation, the disabled/unconfigured no-op, Retry-After
parsing, error redaction and payload minimisation. Queue/flush behaviour
through the outbox is covered against PostgreSQL in
tests/integration/test_n8n_outbox.py and test_n8n_reliability.py.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.integrations.n8n_client import (
    PERSONAL_FIELDS,
    REDELIVERY_REQUIRED_FIELDS,
    _minimal_payload,
    _parse_retry_after,
    _safe_error,
    flush_n8n_events,
    queue_event,
)


class _FakeSession:
    """Stand-in with only `.info`: any attempt to store an outbox row
    (`add`) fails the test, proving the disabled paths write nothing."""

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


NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("120", 120.0),
        (" 7 ", 7.0),
        ("0", 0.0),
        ("Fri, 02 Oct 2026 12:00:30 GMT", 30.0),  # HTTP-date, 30 s ahead
        ("Fri, 02 Oct 2026 11:59:00 GMT", 0.0),  # date in the past: no wait
        ("99999999", 3600.0),  # capped at N8N_RETRY_AFTER_MAX_SECONDS
        ("Sat, 01 Jan 2050 00:00:00 GMT", 3600.0),
    ],
)
def test_retry_after_seconds_and_http_dates_are_parsed_and_capped(
    monkeypatch: pytest.MonkeyPatch, header: str, expected: float
) -> None:
    monkeypatch.setattr(settings, "N8N_RETRY_AFTER_MAX_SECONDS", 3600.0)
    assert _parse_retry_after(header, NOW) == expected


@pytest.mark.parametrize(
    "header",
    [None, "", "soon", "-5", "1.5", "12abc", "\u00b2", "Mon, 99 Foo 2026", 42, b"10", "1" * 11],
)
def test_malformed_retry_after_is_ignored(header: object) -> None:
    assert _parse_retry_after(header, NOW) is None


def test_error_text_is_stripped_of_urls_and_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "N8N_WEBHOOK_URL", "https://hooks.invalid/webhook/abc123")
    monkeypatch.setattr(settings, "N8N_WEBHOOK_SECRET", "s3cr3t-value")
    text = _safe_error(
        "ConnectError: failed https://hooks.invalid/webhook/abc123 "
        "via http://proxy.local:8080/x with s3cr3t-value; token=abcdef api_key: zzz"
    )
    for leaked in ("hooks.invalid", "abc123", "proxy.local", "s3cr3t-value", "abcdef", "zzz"):
        assert leaked not in text
    assert "ConnectError" in text
    assert len(_safe_error("x" * 2000)) == 500


def test_minimal_payload_keeps_only_the_redelivery_contract() -> None:
    full = {
        "event": "JOURNEY_RESOLVED",
        "event_id": "e1",
        "case_id": "c1",
        "journey_id": "j1",
        "timestamp": "2026-10-02T00:00:00+00:00",
        "customer_id": "s1",
        "customer_email": "person@example.com",
        "message": "reviewer text",
    }
    minimal = _minimal_payload(full)
    assert set(minimal) == set(REDELIVERY_REQUIRED_FIELDS)
    assert not set(PERSONAL_FIELDS) & set(minimal)
    assert all(minimal[k] == full[k] for k in REDELIVERY_REQUIRED_FIELDS)
