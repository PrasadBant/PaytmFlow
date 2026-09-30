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


def test_keys_are_independent() -> None:
    lim = SlidingWindowLimiter(FakeClock())
    assert lim.check([("a", 1)]) is None
    assert lim.check([("b", 1)]) is None
    assert lim.check([("a", 1)]) is not None


def _req(xff: str | None, peer: str = "10.0.0.1") -> SimpleNamespace:
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=peer))


@pytest.mark.parametrize(
    ("hops", "xff", "expected"),
    [
        (0, "6.6.6.6, 1.2.3.4", "10.0.0.1"),  # no trusted proxies: header ignored
        (0, None, "10.0.0.1"),
        (1, "6.6.6.6, 1.2.3.4", "1.2.3.4"),  # right-most entry added by our proxy
        (2, "6.6.6.6, 1.2.3.4, 9.9.9.9", "1.2.3.4"),  # spoofed left entry ignored
        (2, "1.2.3.4", "1.2.3.4"),  # shorter chain: nearest proxy's entry
        (3, "6.6.6.6, 1.2.3.4", "1.2.3.4"),  # short chain never falls back to the left
        (1, None, "10.0.0.1"),  # missing header
        (1, "", "10.0.0.1"),
        (1, " , ,", "10.0.0.1"),
        (1, "not-an-ip", "10.0.0.1"),  # malformed value never becomes a bucket key
        (2, "evil, <script>", "10.0.0.1"),
        (1, "2001:db8::1", "2001:db8::1"),
        (1, " 1.2.3.4 ", "1.2.3.4"),
    ],
)
def test_client_ip_counts_trusted_hops_from_the_right(
    monkeypatch: pytest.MonkeyPatch, hops: int, xff: str | None, expected: str
) -> None:
    monkeypatch.setattr(settings, "RATE_LIMIT_TRUSTED_PROXY_HOPS", hops)
    assert client_ip(_req(xff)) == expected  # type: ignore[arg-type]
