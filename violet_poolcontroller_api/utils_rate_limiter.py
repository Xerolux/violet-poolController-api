# violet-poolController-api - API for Violet Pool Controller
# Copyright (C) 2024-2026  Xerolux
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Rate limiter for API requests - token bucket algorithm."""

from __future__ import annotations

import asyncio
import heapq
import logging
import time

_LOGGER = logging.getLogger(__name__)

_STATS_WINDOW_SECONDS = 60


class RateLimiter:
    """Rate Limiter mit Token Bucket Algorithm.

    Verhindert API-Overload durch:
    - Maximale Requests pro Zeitfenster
    - Burst support for short spikes
    - Priority queue for critical requests
    - Graceful degradation once the limit is exceeded
    """

    def __init__(
        self,
        max_requests: int = 10,
        time_window: float = 1.0,
        burst_size: int = 3,
        retry_after: float = 0.1,
    ) -> None:
        """Initialisiere den Rate Limiter.

        Args:
            max_requests: Maximale Anzahl Requests pro Zeitfenster
            time_window: Zeitfenster in Sekunden
            burst_size: Allowed burst size (extra requests).
            retry_after: Seconds to wait once the limit is exceeded.

        """
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        if time_window <= 0:
            raise ValueError("time_window must be greater than zero")
        if burst_size < 0:
            raise ValueError("burst_size must not be negative")
        if retry_after <= 0:
            raise ValueError("retry_after must be greater than zero")

        self.max_requests = max_requests
        self.time_window = time_window
        self.burst_size = burst_size
        self.retry_after = retry_after

        # Token Bucket
        self.tokens = float(max_requests + burst_size)
        self.max_tokens = max_requests + burst_size
        self.last_refill = time.monotonic()

        self.blocked_requests = 0
        self.total_requests = 0

        # Memory-efficient statistics
        self._recent_stats = {
            "requests_last_minute": 0,
            "blocked_last_minute": 0,
            "last_minute_reset": time.monotonic(),
        }

        # Lock for thread safety
        self._lock = asyncio.Lock()
        self._waiters: list[tuple[int, int, asyncio.Event]] = []
        self._waiter_sequence = 0

        _LOGGER.debug(
            "Rate limiter initialized: %d req/%ss (burst: %d)",
            max_requests,
            time_window,
            burst_size,
        )

    async def acquire(self, priority: int = 3) -> bool:
        """Acquire a token from the rate limiter.

        Args:
            priority: Priority level (0=highest, 3=lowest)

        Returns:
            True if token acquired, False otherwise

        """
        async with self._lock:
            current_time = time.monotonic()
            self._record_request(current_time)
            if not self._waiters and self._consume_token(priority, current_time):
                return True

            self._record_blocked_request()
            return False

    def _record_request(self, current_time: float) -> None:
        self.total_requests += 1
        self._reset_recent_stats_if_needed(current_time)
        self._recent_stats["requests_last_minute"] += 1

    def _record_blocked_request(self) -> None:
        self.blocked_requests += 1
        self._recent_stats["blocked_last_minute"] += 1

    def _consume_token(self, priority: int, current_time: float) -> bool:  # noqa: ARG002
        self._refill_tokens(current_time)
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True

    def _reset_recent_stats_if_needed(self, current_time: float) -> None:
        """Reset recent statistics after their rolling window expires."""
        if current_time - self._recent_stats["last_minute_reset"] > _STATS_WINDOW_SECONDS:
            self._recent_stats["requests_last_minute"] = 0
            self._recent_stats["blocked_last_minute"] = 0
            self._recent_stats["last_minute_reset"] = current_time

    async def wait_if_needed(self, priority: int = 3, timeout: float = 10.0) -> None:  # noqa: ASYNC109
        """Wait until a token is available.

        Args:
            priority: The request priority.
            timeout: Maximum time to wait, in seconds.

        Raises:
            TimeoutError: If the timeout is reached

        """
        start_time = time.monotonic()
        event = asyncio.Event()
        queued = False

        async with self._lock:
            current_time = time.monotonic()
            self._record_request(current_time)
            if not self._waiters and self._consume_token(priority, current_time):
                return
            self._record_blocked_request()
            waiter = (priority, self._waiter_sequence, event)
            self._waiter_sequence += 1
            heapq.heappush(self._waiters, waiter)
            queued = True

        try:
            while True:
                async with self._lock:
                    current_time = time.monotonic()
                    is_head = bool(self._waiters and self._waiters[0] == waiter)
                    if is_head:
                        if self._consume_token(priority, current_time):
                            heapq.heappop(self._waiters)
                            queued = False
                            if self._waiters:
                                self._waiters[0][2].set()
                            return
                    event.clear()
                    if is_head:
                        refill_rate = self.max_requests / self.time_window
                        needed_tokens = max(0.0, 1.0 - self.tokens)
                        wait_time = min(
                            max(needed_tokens / refill_rate, 0.001),
                            self.retry_after,
                        )
                    else:
                        wait_time = self.retry_after

                elapsed = time.monotonic() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    msg = f"Rate Limiter timeout nach {elapsed:.1f}s"
                    raise TimeoutError(msg)
                try:
                    await asyncio.wait_for(event.wait(), timeout=min(wait_time, remaining))
                except TimeoutError:
                    continue
        finally:
            if queued:
                async with self._lock:
                    if waiter in self._waiters:
                        self._waiters.remove(waiter)
                        heapq.heapify(self._waiters)
                        if self._waiters:
                            self._waiters[0][2].set()

    def _refill_tokens(self, current_time: float) -> None:
        """Refill the token bucket according to the elapsed time."""
        time_passed = current_time - self.last_refill

        # Refill proportional to time passed, not just when full window elapsed
        if time_passed > 0:
            # Berechne neue Tokens basierend auf verstrichener Zeit
            refill_rate = self.max_requests / self.time_window
            new_tokens = time_passed * refill_rate

            self.tokens = min(self.max_tokens, self.tokens + new_tokens)
            self.last_refill = current_time

    def get_stats(self) -> dict:
        """Return a snapshot of the limiter's counters.

        ``current_tokens`` is computed for *now* without mutating the bucket;
        reading ``self.tokens`` directly reported a stale value that looked
        like an exhausted limiter after an idle period.
        """
        current_time = time.monotonic()
        refill_rate = self.max_requests / self.time_window
        tokens_now = min(
            float(self.max_tokens),
            self.tokens + max(0.0, current_time - self.last_refill) * refill_rate,
        )
        recent_window_expired = (
            current_time - self._recent_stats["last_minute_reset"] > _STATS_WINDOW_SECONDS
        )

        return {
            "total_requests": self.total_requests,
            "blocked_requests": self.blocked_requests,
            "recent_requests_1min": (
                0 if recent_window_expired else self._recent_stats["requests_last_minute"]
            ),
            "recent_blocked_1min": (
                0 if recent_window_expired else self._recent_stats["blocked_last_minute"]
            ),
            "current_tokens": tokens_now,
            "max_tokens": self.max_tokens,
            "block_rate": (
                self.blocked_requests / self.total_requests * 100 if self.total_requests > 0 else 0
            ),
        }

    def reset(self) -> None:
        """Reset the rate limiter."""
        self.tokens = float(self.max_tokens)
        self.last_refill = time.monotonic()
        self.blocked_requests = 0
        self.total_requests = 0
        for _, _, event in self._waiters:
            event.set()
        self._recent_stats["requests_last_minute"] = 0
        self._recent_stats["blocked_last_minute"] = 0
        self._recent_stats["last_minute_reset"] = time.monotonic()
        _LOGGER.debug("Rate limiter reset")


# Global rate limiter instance (one can also be created per API instance)
_global_rate_limiter: RateLimiter | None = None


def get_global_rate_limiter() -> RateLimiter:
    """Hole oder erstelle globalen Rate Limiter."""
    global _global_rate_limiter  # noqa: PLW0603
    if _global_rate_limiter is None:
        # Default-Werte aus const_api
        from .const_api import (  # noqa: PLC0415
            API_RATE_LIMIT_BURST,
            API_RATE_LIMIT_REQUESTS,
            API_RATE_LIMIT_RETRY_AFTER,
            API_RATE_LIMIT_WINDOW,
        )

        _global_rate_limiter = RateLimiter(
            max_requests=API_RATE_LIMIT_REQUESTS,
            time_window=API_RATE_LIMIT_WINDOW,
            burst_size=API_RATE_LIMIT_BURST,
            retry_after=API_RATE_LIMIT_RETRY_AFTER,
        )
    return _global_rate_limiter


__all__ = ["RateLimiter", "get_global_rate_limiter"]
