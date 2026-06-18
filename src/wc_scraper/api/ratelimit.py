"""Tiered fixed-window rate limiting (in-memory, single instance).

Guests are limited by client IP; authenticated callers by their API key, at a higher rate.
This is intentionally simple; the identity/limit seam makes swapping in a Redis-backed
store straightforward later for multi-instance deployments.
"""

from __future__ import annotations

import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import api_settings
from .security import extract_token

_WINDOW_SECONDS = 60


class _FixedWindowCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}  # identity -> (window_start, count)

    def hit(self, identity: str, limit: int, now: float) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        window = int(now) // _WINDOW_SECONDS
        with self._lock:
            start, count = self._hits.get(identity, (window, 0))
            if start != window:
                start, count = window, 0
            count += 1
            self._hits[identity] = (start, count)
        if count > limit:
            retry_after = _WINDOW_SECONDS - (int(now) % _WINDOW_SECONDS)
            return False, retry_after
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Identify the caller (key vs IP), pick the tier, enforce a per-minute window."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._counter = _FixedWindowCounter()

    async def dispatch(self, request: Request, call_next):
        token = extract_token(request)
        if token:
            identity, limit = f"key:{token[-16:]}", api_settings.client_rpm
        else:
            client = request.client
            identity = f"ip:{client.host if client else 'unknown'}"
            limit = api_settings.guest_rpm

        allowed, retry_after = self._counter.hit(identity, limit, time.time())
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded.", "limit_per_minute": limit},
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response
