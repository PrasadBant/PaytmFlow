"""Rate limits on the paid AI endpoints: normal use passes, excess gets 429
with Retry-After, buckets are per session and per client IP."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.fixture
def tight_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_CHAT_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRANSLATE_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 100)
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 1000)


async def _chat(client: AsyncClient, headers: dict) -> int:
    r = await client.post("/api/v1/chat", json={"message": "Which documents?"}, headers=headers)
    return r.status_code


async def test_normal_chat_usage_is_not_limited(
    client: AsyncClient, session_headers: dict, tight_limits: None
) -> None:
    assert [await _chat(client, session_headers) for _ in range(3)] == [200, 200, 200]


async def test_exceeding_chat_limit_returns_429_with_retry_after(
    client: AsyncClient, session_headers: dict, tight_limits: None
) -> None:
    for _ in range(3):
        assert await _chat(client, session_headers) == 200
    r = await client.post("/api/v1/chat", json={"message": "hello"}, headers=session_headers)
    assert r.status_code == 429
    error = r.json()["error"]
    assert error["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) >= 1
    assert error["details"]["retry_after_seconds"] == int(r.headers["Retry-After"])


async def test_limit_is_per_session(
    client: AsyncClient, session_headers: dict, other_session_headers: dict, tight_limits: None
) -> None:
    for _ in range(3):
        await _chat(client, session_headers)
    assert await _chat(client, session_headers) == 429
    assert await _chat(client, other_session_headers) == 200


async def test_journey_chat_shares_the_session_chat_bucket(
    client: AsyncClient, session_headers: dict, tight_limits: None
) -> None:
    r = await client.post(
        "/api/v1/journeys",
        json={
            "journey_type": "LENDING",
            "goal": {"loan_amount": 250000, "loan_purpose": "EDUCATION", "tenure_months": 36},
        },
        headers=session_headers,
    )
    jid = r.json()["journey_id"]
    for _ in range(3):
        assert await _chat(client, session_headers) == 200
    r = await client.post(
        f"/api/v1/journeys/{jid}/chat", json={"message": "why?"}, headers=session_headers
    )
    assert r.status_code == 429


async def test_translate_limited_independently_of_chat(
    client: AsyncClient, session_headers: dict, tight_limits: None
) -> None:
    body = {"text": "hello", "target_language_code": "hi-IN"}
    # Translation is disabled in tests (404), but the limiter runs first.
    codes = [
        (await client.post("/api/v1/translate", json=body, headers=session_headers)).status_code
        for _ in range(3)
    ]
    assert 429 not in codes[:2] and codes[2] == 429
    assert await _chat(client, session_headers) == 200


async def test_per_ip_ceiling_stops_cookie_shedding(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 4)
    codes = [await _chat(client, {"X-Session-Id": str(uuid4())}) for _ in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]


async def test_forwarded_for_behind_trusted_proxies_separates_clients(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 2)

    def hdrs(client_addr: str, spoof: str = "") -> dict:
        chain = ", ".join(p for p in (spoof, client_addr, "76.76.21.1") if p)
        return {"X-Session-Id": str(uuid4()), "X-Forwarded-For": chain}

    assert await _chat(client, hdrs("1.1.1.1")) == 200
    assert await _chat(client, hdrs("1.1.1.1")) == 200
    assert await _chat(client, hdrs("1.1.1.1")) == 429
    # A client prepending fake addresses is still keyed on its real address.
    assert await _chat(client, hdrs("1.1.1.1", spoof="8.8.8.8")) == 429
    assert await _chat(client, hdrs("2.2.2.2")) == 200


async def test_global_ceiling_holds_against_spoofed_ips_and_new_sessions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
    codes = [
        await _chat(client, {"X-Session-Id": str(uuid4()), "X-Forwarded-For": f"203.0.113.{i}"})
        for i in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]


async def test_spoofed_header_ignored_without_trusted_proxies(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 0)
    codes = [
        await _chat(client, {"X-Session-Id": str(uuid4()), "X-Forwarded-For": f"198.51.100.{i}"})
        for i in range(3)
    ]
    # Rotating the header does not create new buckets: all share the peer's.
    assert codes == [200, 200, 429]


async def test_missing_forwarded_header_behind_proxy_falls_back_to_peer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 2)
    assert await _chat(client, {"X-Session-Id": str(uuid4())}) == 200
    assert await _chat(client, {"X-Session-Id": str(uuid4())}) == 429


async def test_disabled_limiter_never_blocks(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    codes = [await _chat(client, session_headers) for _ in range(6)]
    assert codes == [200] * 6
