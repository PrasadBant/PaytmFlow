"""Rate limits for the paid AI endpoints
(/chat, /journeys/{id}/chat, /journeys/{id}/chat/voice, /translate) and for
reviewer access-code attempts (/review/role, in its own pool).

Sliding window, in process memory: limits hold per API worker, so a
multi-instance deployment multiplies the effective ceiling by the instance
count (a shared store such as Redis would be needed for a global limit).

Three buckets per request, all must have room:
- session: the signed pf_session id. A client can shed its cookie to get a
  new session, so this alone is not a defence.
- client IP: taken from X-Forwarded-For, counting RATE_LIMIT_TRUSTED_PROXY_HOPS
  entries from the RIGHT (entries appended by proxies we control). Left-hand
  entries are client-supplied and never trusted. With 0 hops, the TCP peer
  address is used. Applied only when that address is public: a private peer
  is a proxy, and one shared bucket would let one client lock everyone out.
  Behind a proxy chain that can also be bypassed (e.g. a Vercel rewrite in
  front of a publicly reachable Render URL) no hop count is right for both
  paths, so this bucket is best-effort.
- global: one ceiling for all callers of this instance. It cannot be dodged by
  spoofing headers or shedding cookies, so it bounds paid-API spend regardless.
"""

from __future__ import annotations

import ipaddress
import math
import time
from collections import deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.db.models import SessionModel
from app.schemas.enums import ErrorCode
from app.schemas.errors import ErrorEnvelope, ErrorObject
from app.security.session import get_current_session

WINDOW_SECONDS = 60.0
# Bound on tracked keys so a flood of distinct keys cannot exhaust memory.
_MAX_KEYS = 50_000


class SlidingWindowLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, keys: list[tuple[str, int]]) -> float | None:
        """Records one hit against every key when all have room; otherwise
        records nothing and returns the seconds until the tightest one frees."""
        now = self._clock()
        cutoff = now - WINDOW_SECONDS
        retry_after = 0.0
        for key, limit in keys:
            if limit <= 0:
                # A limit of 0 (or a bad negative value) means "allow none":
                # fail closed rather than let the first request through.
                retry_after = max(retry_after, WINDOW_SECONDS)
                continue
            hits = self._hits.get(key)
            if hits is None:
                continue
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(retry_after, hits[0] + WINDOW_SECONDS - now)
        if retry_after > 0:
            return retry_after
        if len(self._hits) > _MAX_KEYS:
            self._evict(cutoff)
        for key, _limit in keys:
            self._hits.setdefault(key, deque()).append(now)
        return None

    def _evict(self, cutoff: float) -> None:
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def client_ip(request: Request) -> str | None:
    """The address that identifies this client, or None when none does.

    Only a public (globally routable) address is returned. A private,
    loopback or otherwise non-public address is almost always a proxy or load
    balancer in front of the API; keying on it would make every user share
    one bucket, so one abusive client could lock everyone out. The per-IP
    bucket is then skipped and the session and global buckets still apply."""
    hops = settings.RATE_LIMIT_TRUSTED_PROXY_HOPS
    peer = request.client.host if request.client else ""
    candidate = peer
    if hops > 0:
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if forwarded:
            # Fewer entries than trusted proxies: the request skipped part of the
            # chain. The right-most entry was still added by the proxy nearest to
            # us, whereas anything further left may have been written by the client.
            candidate = forwarded[-hops] if len(forwarded) >= hops else forwarded[-1]
    ip = _valid_ip(candidate)
    if ip is None or not ipaddress.ip_address(ip).is_global:
        return None
    return ip


def rate_limited(
    scope: str,
    per_session_setting: str,
    *,
    pool: str = "ai",
    ip_setting: str = "RATE_LIMIT_IP_PER_MINUTE",
    global_setting: str = "RATE_LIMIT_GLOBAL_PER_MINUTE",
) -> Callable[..., object]:
    """FastAPI dependency factory. The *_setting arguments name Settings fields,
    read per request so tests and env overrides take effect without
    re-importing routers. `pool` groups endpoints that share the per-IP and
    global buckets (all paid AI endpoints share "ai")."""

    async def dependency(
        request: Request,
        session: SessionModel = Depends(get_current_session),
    ) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        buckets = [
            (f"{scope}:s:{session.id}", int(getattr(settings, per_session_setting))),
            (f"{pool}:global", int(getattr(settings, global_setting))),
        ]
        ip = client_ip(request)
        if ip is not None:
            buckets.append((f"{pool}:ip:{ip}", int(getattr(settings, ip_setting))))
        retry_after = limiter.check(buckets)
        if retry_after is None:
            return
        raise HTTPException(
            status_code=429,
            detail=ErrorEnvelope(
                error=ErrorObject(
                    code=ErrorCode.RATE_LIMITED,
                    message="Too many requests. Please wait a moment and try again.",
                    details={"retry_after_seconds": math.ceil(retry_after)},
                )
            ).model_dump(mode="json"),
            headers={"Retry-After": str(math.ceil(retry_after))},
        )

    return dependency
