"""Rate limits on the paid AI endpoints: normal use passes, excess gets 429
with Retry-After, buckets are per session and per client IP."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app

PUBLIC_PEER = "34.1.2.3"


@pytest.fixture
def tight_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_CHAT_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRANSLATE_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 100)
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 1000)


@pytest.fixture
async def public_client(client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Same app and test database as `client`, but connecting from a public
    address - as a client reaching the API directly, with no proxy."""
    async with AsyncClient(
        transport=ASGITransport(app=app, client=(PUBLIC_PEER, 40000)), base_url="http://test"
    ) as c:
        yield c


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
    public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 4)
    codes = [await _chat(public_client, {"X-Session-Id": str(uuid4())}) for _ in range(6)]
    assert codes == [200, 200, 200, 200, 429, 429]


async def test_users_behind_a_private_proxy_do_not_share_one_ip_bucket(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    # `client` connects from 127.0.0.1, standing in for the platform load
    # balancer with RATE_LIMIT_TRUSTED_PROXY_HOPS=0. Keying on it would let a
    # handful of requests lock every user out; only session/global apply.
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 0)
    codes = [await _chat(client, {"X-Session-Id": str(uuid4())}) for _ in range(5)]
    assert codes == [200] * 5


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
    # A different real client has its own bucket.
    assert await _chat(client, hdrs("2.2.2.2")) == 200


async def test_global_ceiling_holds_against_spoofed_ips_and_new_sessions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
    codes = [
        await _chat(client, {"X-Session-Id": str(uuid4()), "X-Forwarded-For": f"8.8.4.{i}"})
        for i in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]


async def test_spoofed_header_from_a_direct_client_is_ignored_without_trusted_proxies(
    public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 0)
    codes = [
        await _chat(public_client, {"X-Session-Id": str(uuid4()), "X-Forwarded-For": f"9.9.9.{i}"})
        for i in range(3)
    ]
    # Rotating the header does not create new buckets: all share the real peer's.
    assert codes == [200, 200, 429]


async def test_direct_request_spoofing_a_trusted_chain_is_the_documented_gap(
    public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    # With hops=1 configured for a proxy, a client that bypasses the proxy and
    # writes its own X-Forwarded-For picks its bucket key. This pins down the
    # known limitation; the session and global buckets still bound it.
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 1)
    codes = [
        await _chat(public_client, {"X-Session-Id": str(uuid4()), "X-Forwarded-For": f"9.9.9.{i}"})
        for i in range(4)
    ]
    assert codes == [200, 200, 200, 429]  # per-IP dodged, global still holds


async def test_missing_forwarded_header_behind_proxy_falls_back_to_peer(
    public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_PER_MINUTE", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 2)
    assert await _chat(public_client, {"X-Session-Id": str(uuid4())}) == 200
    assert await _chat(public_client, {"X-Session-Id": str(uuid4())}) == 429


async def test_reviewer_code_guessing_is_rate_limited(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "correct-reviewer-code-0123456789")
    monkeypatch.setattr(settings, "RATE_LIMIT_REVIEWER_ROLE_PER_MINUTE", 3)
    codes = []
    for i in range(5):
        r = await client.post(
            "/api/v1/review/role",
            json={"role": "REVIEW_OFFICER", "access_code": f"guess-{i}"},
            headers=session_headers,
        )
        codes.append(r.status_code)
    assert codes == [403, 403, 403, 429, 429]
    blocked = await client.post(
        "/api/v1/review/role",
        json={"role": "REVIEW_OFFICER", "access_code": "correct-reviewer-code-0123456789"},
        headers=session_headers,
    )
    assert blocked.status_code == 429  # even the right code waits out the window
    assert int(blocked.headers["Retry-After"]) >= 1


async def _guess_with_fresh_session(client: AsyncClient, i: int) -> int:
    r = await client.post(
        "/api/v1/review/role",
        json={"role": "REVIEW_OFFICER", "access_code": f"guess-{i}"},
        headers={"X-Session-Id": str(uuid4())},
    )
    return r.status_code


async def test_reviewer_guessing_with_new_sessions_behind_a_proxy_hits_the_global_cap(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The likely production path: the API sees only the platform proxy (a
    # private peer, so no per-IP bucket) and the attacker drops its cookie on
    # every guess. Only the per-instance reviewer ceiling bounds it.
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "correct-reviewer-code-0123456789")
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", 0)
    monkeypatch.setattr(settings, "RATE_LIMIT_REVIEWER_ROLE_GLOBAL_PER_MINUTE", 4)
    codes = [await _guess_with_fresh_session(client, i) for i in range(6)]
    assert codes == [403, 403, 403, 403, 429, 429]


async def test_reviewer_guessing_from_one_public_address_hits_the_ip_cap(
    public_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "REVIEWER_ACCESS_CODE", "correct-reviewer-code-0123456789")
    monkeypatch.setattr(settings, "RATE_LIMIT_REVIEWER_ROLE_IP_PER_MINUTE", 3)
    codes = [await _guess_with_fresh_session(public_client, i) for i in range(5)]
    assert codes == [403, 403, 403, 429, 429]


async def test_reviewer_role_pool_is_separate_from_ai_endpoints(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_GLOBAL_PER_MINUTE", 1)
    assert await _chat(client, session_headers) == 200
    assert await _chat(client, session_headers) == 429  # AI pool exhausted
    r = await client.post("/api/v1/review/role", json={"role": "CUSTOMER"}, headers=session_headers)
    assert r.status_code == 200


async def test_disabled_limiter_never_blocks(
    client: AsyncClient, session_headers: dict, monkeypatch: pytest.MonkeyPatch, tight_limits: None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    codes = [await _chat(client, session_headers) for _ in range(6)]
    assert codes == [200] * 6
