"""Rate limiter + HTTP 429 retry helpers.

Token-bucket based rate limiter configurable per service.
Exponential backoff for 429 (Too Many Requests) responses.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TokenBucket:
    """Simple token-bucket rate limiter.

    Allows up to ``capacity`` requests in a sliding window of ``window_sec``.
    """

    __slots__ = ("capacity", "window_sec", "_tokens", "_last_refill")

    def __init__(self, capacity: int, window_sec: float = 3600.0) -> None:
        self.capacity = capacity
        self.window_sec = window_sec
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self.capacity),
            self._tokens + elapsed / self.window_sec * self.capacity,
        )
        self._last_refill = now

    def acquire(self, tokens: float = 1.0, block: bool = True) -> bool:
        """Acquire *tokens* (default 1 request).

        If *block* is True, busy-wait until tokens are available.
        Returns True if acquired (always True when block=True).
        """
        if tokens <= 0:
            return True
        while True:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            if not block:
                return False
            sleep_sec = (tokens - self._tokens) * self.window_sec / self.capacity
            time.sleep(max(sleep_sec, 0.01))


def retry_on_429(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: retry a callable on 429 HTTP errors.

    Uses exponential backoff:
        delay = min(base_delay * 2^attempt, max_delay) * (1 + jitter*random())

    The decorated function must raise a ``RuntimeError`` whose message
    contains "HTTP error 429", "rate limit", or "too many requests".

    Returns the first successful result.  If all retries fail, raises
    ``RuntimeError("Request failed after N retries")``.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except RuntimeError as exc:
                    last_exc = exc
                    msg = str(exc)
                    is_429 = (
                        "HTTP error 429" in msg
                        or "rate limit" in msg.lower()
                        or "too many requests" in msg.lower()
                    )
                    if is_429 and attempt < max_retries:
                        delay = min(base_delay * (2**attempt), max_delay)
                        if jitter:
                            delay *= 1.0 + random.random() * 0.5
                        logger.warning(
                            "429 detected, retry %d/%d in %.1fs: %s",
                            attempt + 1,
                            max_retries,
                            delay,
                            msg[:120],
                        )
                        time.sleep(delay)
                        continue
                    # On the last attempt, let the loop finish so the
                    # ``else`` clause fires with a proper message.
                    if attempt >= max_retries:
                        continue
                    # Non-429 on a non-last attempt — raise immediately
                    raise
            else:
                raise RuntimeError(
                    f"Request failed after {max_retries} retries"
                ) from last_exc

        return wrapper

    return decorator


__all__ = ["TokenBucket", "retry_on_429"]
