from types import SimpleNamespace

import pytest

from app.config import settings
from app.security.rate_limit import WINDOW_SECONDS, SlidingWindowLimiter, client_ip


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_limit_then_blocks_with_retry_after() -> None:
    lim = SlidingWindowLimiter(FakeClock())
    for _ in range(3):
        assert lim.check([("k", 3)]) is None
    retry = lim.check([("k", 3)])
    assert retry is not None and 0 < retry <= WINDOW_SECONDS


def test_window_slides_and_frees_capacity() -> None:
    clock = FakeClock()
    lim = SlidingWindowLimiter(clock)
    assert lim.check([("k", 1)]) is None
    clock.now += 30
    assert lim.check([("k", 1)]) is not None
    clock.now += WINDOW_SECONDS - 30 + 0.01
    assert lim.check([("k", 1)]) is None


def test_blocked_request_is_not_counted_against_any_bucket() -> None:
    lim = SlidingWindowLimiter(FakeClock())
    assert lim.check([("session", 5), ("ip", 1)]) is None
    # IP full: rejected, and the session bucket must not be charged for it.
    for _ in range(10):
        assert lim.check([("session", 5), ("ip", 1)]) is not None
    assert lim.check([("session", 5), ("other-ip", 1)]) is None
    assert len(lim._hits["session"]) == 2


@pytest.mark.parametrize("limit", [0, -1])
def test_zero_or_negative_limit_blocks_every_request_without_crashing(limit: int) -> None:
    clock = FakeClock()
    lim = SlidingWindowLimiter(clock)
    assert lim.check([("k", limit)]) == WINDOW_SECONDS
    assert lim.check([("k", limit), ("other", 5)]) == WINDOW_SECONDS
    clock.now += WINDOW_SECONDS * 2
    assert lim.check([("k", limit)]) == WINDOW_SECONDS
    assert "other" not in lim._hits  # a blocked request charges no bucket


def test_keys_are_independent() -> None:
    lim = SlidingWindowLimiter(FakeClock())
    assert lim.check([("a", 1)]) is None
    assert lim.check([("b", 1)]) is None
    assert lim.check([("a", 1)]) is not None


def _req(xff: str | None, peer: str = "34.1.2.3") -> SimpleNamespace:
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


PUBLIC_PEER = "34.1.2.3"


@pytest.mark.parametrize(
    ("hops", "xff", "peer", "expected"),
    [
        # No trusted proxies: the header is ignored, the TCP peer is the client.
        (0, "6.6.6.6, 1.2.3.4", PUBLIC_PEER, PUBLIC_PEER),
        (0, None, PUBLIC_PEER, PUBLIC_PEER),
        # Trusted proxies: count from the right; client-written entries ignored.
        (1, "6.6.6.6, 1.2.3.4", PUBLIC_PEER, "1.2.3.4"),
        (2, "6.6.6.6, 1.2.3.4, 9.9.9.9", PUBLIC_PEER, "1.2.3.4"),
        (2, "1.2.3.4", PUBLIC_PEER, "1.2.3.4"),  # short chain: nearest proxy's entry
        (3, "6.6.6.6, 1.2.3.4", PUBLIC_PEER, "1.2.3.4"),  # never falls back to the left
        (1, " 1.2.3.4 ", PUBLIC_PEER, "1.2.3.4"),
        (1, "2606:4700::1111", PUBLIC_PEER, "2606:4700::1111"),
        # Missing or malformed header: fall back to the peer / no key.
        (1, None, PUBLIC_PEER, PUBLIC_PEER),
        (1, "", PUBLIC_PEER, PUBLIC_PEER),
        (1, " , ,", PUBLIC_PEER, PUBLIC_PEER),
        (1, "not-an-ip", PUBLIC_PEER, None),  # malformed never becomes a bucket key
        (2, "evil, <script>", PUBLIC_PEER, None),
        # Non-public addresses identify a proxy, not a user: no per-IP bucket.
        (0, None, "10.0.0.1", None),  # e.g. the platform load balancer
        (0, None, "127.0.0.1", None),
        (0, "1.2.3.4", "10.0.0.1", None),  # header still ignored without trusted hops
        (1, "192.168.1.5", PUBLIC_PEER, None),
        (1, "2001:db8::1", PUBLIC_PEER, None),  # documentation range
        (1, None, "10.0.0.1", None),
        (0, None, "", None),  # no peer information at all
    ],
)
def test_client_ip_only_returns_an_address_that_identifies_a_client(
    monkeypatch: pytest.MonkeyPatch, hops: int, xff: str | None, peer: str, expected: str | None
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", hops)
    assert client_ip(_req(xff, peer)) == expected  # type: ignore[arg-type]
