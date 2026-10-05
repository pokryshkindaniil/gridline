"""Process-local rate limiting for feed mutations."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .config import get_settings


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0, now: float | None = None) -> float | None:
        """Return None if allowed, else seconds until the next slot frees up."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= window:
                q.popleft()
            if len(q) >= limit:
                return window - (now - q[0])
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= window]:
                    del self._hits[k]
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """Return the address used as the rate-limit key."""
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for", "")
        # Only trust the value appended by the configured reverse proxy.
        ip = _valid_ip(fwd.split(",")[-1]) if fwd else None
        if ip:
            return ip
    return request.client.host if request.client else "unknown"


def feed_mutation_limit(request: Request) -> None:
    retry = limiter.check(client_ip(request), get_settings().feed_rate_limit_per_minute)
    if retry is not None:
        raise HTTPException(429, "too many requests", headers={"Retry-After": str(int(retry) + 1)})
