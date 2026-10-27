"""In-memory rate limits for the public endpoints that spend Claude tokens.

/run, /chat and the two session starters are public and unauthenticated, so
without a limit anyone can drain the Anthropic budget or try booking codes.

In-memory is enough because the API runs as ONE uvicorn process -- it has to,
since SessionStore is a process dict too. A second worker would need both
moved to a shared store.

The client IP is `request.client.host`. Behind Nginx that is only the visitor's
address if Nginx sets X-Forwarded-For and uvicorn trusts it (it trusts
127.0.0.1 by default); otherwise every visitor shares Nginx's IP and one
limit for the whole world.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Callable

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitError

_MINUTE = 60
_DAY = 24 * 60 * 60


class RateLimiter:
    """Sliding-window counters keyed by an arbitrary string."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def _window(self, key: str, seconds: int, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= seconds:
            hits.popleft()
        return hits

    def hit(self, key: str, limit: int, seconds: int) -> None:
        """Record one request, or raise RateLimitError if the window is full.

        A refused request is not recorded, so retrying after Retry-After works.
        """
        with self._lock:
            now = self._clock()
            hits = self._window(key, seconds, now)
            if len(hits) >= limit:
                retry = max(1, math.ceil(seconds - (now - hits[0])))
                raise RateLimitError(
                    retry_after=retry,
                    log_message=f"rate limit {key}: {limit}/{seconds}s",
                )
            hits.append(now)

    def count(self, key: str, seconds: int) -> int:
        with self._lock:
            return len(self._window(key, seconds, self._clock()))

    def record(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, deque()).append(self._clock())

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enabled() -> bool:
    return get_settings().rate_limit_enabled


def _global_agent_cap() -> None:
    # Checked after the per-IP limits, so a refused visitor does not use up
    # the day's shared budget. Catches abuse spread across many IPs.
    settings = get_settings()
    try:
        limiter.hit("global:agent", settings.rate_agent_global_per_day, _DAY)
    except RateLimitError as exc:
        raise RateLimitError(
            detail=(
                "El asistente alcanzo su limite de uso por hoy. "
                "Intenta de nuevo manana."
            ),
            code="limite_diario_global",
            retry_after=exc.retry_after,
            log_message="global daily agent cap reached",
        ) from exc


# FastAPI dependencies, one per endpoint family.

def limit_session_start(request: Request) -> None:
    if not _enabled():
        return
    settings = get_settings()
    limiter.hit(
        f"start:{client_ip(request)}",
        settings.rate_session_start_per_10min,
        10 * _MINUTE,
    )


def limit_run(request: Request) -> None:
    if not _enabled():
        return
    settings = get_settings()
    ip = client_ip(request)
    limiter.hit(f"run10:{ip}", settings.rate_run_per_10min, 10 * _MINUTE)
    limiter.hit(f"runday:{ip}", settings.rate_run_per_day, _DAY)
    _global_agent_cap()


def limit_chat(request: Request) -> None:
    if not _enabled():
        return
    settings = get_settings()
    ip = client_ip(request)
    limiter.hit(f"chatmin:{ip}", settings.rate_chat_per_minute, _MINUTE)
    limiter.hit(f"chatday:{ip}", settings.rate_chat_per_day, _DAY)
    _global_agent_cap()


# Booking-lookup lockout, used by the appointment tools' shared _verify().

def verify_locked(session_id: str | None) -> bool:
    if not session_id or not _enabled():
        return False
    settings = get_settings()
    return (
        limiter.count(f"verify:{session_id}", settings.session_ttl_minutes * _MINUTE)
        >= settings.verify_max_failures
    )


def record_verify_failure(session_id: str | None) -> None:
    if session_id:
        limiter.record(f"verify:{session_id}")
