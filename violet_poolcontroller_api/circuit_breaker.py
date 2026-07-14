# violet-poolController-api - API für Violet Pool Controller
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


"""Circuit breaker implementation for resilient API calls."""

from __future__ import annotations

import asyncio
import logging
import time
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class CircuitBreakerState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"  # Normal operation
    OPEN = "OPEN"  # Circuit is open, calls fail fast
    HALF_OPEN = "HALF_OPEN"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker pattern for API calls with automatic recovery.

    Protects against cascading failures when the controller or network is down.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        recovery_timeout: float = 300.0,
        expected_exception: type[BaseException] = Exception,
        ignored_exceptions: tuple[type[BaseException], ...] = (),
    ) -> None:
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: How long to keep circuit open (seconds)
            recovery_timeout: How long to stay in half-open state
            expected_exception: Exception type to consider for failures
            ignored_exceptions: Exception types that pass through without
                affecting the failure count (e.g. deterministic client
                errors that do not indicate an unavailable service)

        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.ignored_exceptions = ignored_exceptions

        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitBreakerState.CLOSED
        self.half_open_start_time = 0.0
        self._half_open_probe_in_flight = False

        # Protects mutable state from concurrent coroutine access (e.g., asyncio.gather)
        self._lock = asyncio.Lock()

        _LOGGER.debug(
            "Circuit breaker initialized: threshold=%d, timeout=%.1fs, recovery=%.1fs",
            failure_threshold,
            timeout,
            recovery_timeout,
        )

    async def call(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Execute function with circuit breaker protection.

        Args:
            func: The async function to call
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function

        Returns:
            Result of function call

        Raises:
            CircuitBreakerOpenError: If circuit is open

        """
        is_half_open_probe = False

        async with self._lock:
            current_time = time.monotonic()
            if (
                self.state == CircuitBreakerState.OPEN
                and current_time - self.last_failure_time > self.timeout
            ):
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_start_time = current_time
                self._half_open_probe_in_flight = False
                _LOGGER.info(
                    "Circuit breaker entering HALF_OPEN state for recovery test",
                )

            if self.state == CircuitBreakerState.OPEN:
                msg = "Circuit breaker is OPEN"
                raise CircuitBreakerOpenError(msg)

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    msg = "Circuit breaker recovery probe is already running"
                    raise CircuitBreakerOpenError(msg)
                self._half_open_probe_in_flight = True
                is_half_open_probe = True

        try:
            if is_half_open_probe and self.recovery_timeout > 0:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.recovery_timeout,
                )
            else:
                result = await func(*args, **kwargs)

        except self.ignored_exceptions:
            if is_half_open_probe:
                async with self._lock:
                    self._half_open_probe_in_flight = False
            raise

        except asyncio.CancelledError:
            if is_half_open_probe:
                async with self._lock:
                    self._half_open_probe_in_flight = False
            raise

        except (self.expected_exception, TimeoutError) as err:
            async with self._lock:
                failure_time = time.monotonic()
                self.failure_count += 1
                self.last_failure_time = failure_time
                self._half_open_probe_in_flight = False

                _LOGGER.debug(
                    "Circuit breaker failure %d/%d: %s",
                    self.failure_count,
                    self.failure_threshold,
                    str(err),
                )

                if is_half_open_probe or self.failure_count >= self.failure_threshold:
                    self.state = CircuitBreakerState.OPEN
                    _LOGGER.warning(
                        "Circuit breaker OPENED due to %d failures",
                        self.failure_threshold,
                    )

            raise

        except Exception:
            if is_half_open_probe:
                async with self._lock:
                    self._half_open_probe_in_flight = False
            _LOGGER.exception("Unhandled exception escaped circuit breaker")
            raise

        else:
            async with self._lock:
                if is_half_open_probe and self.state == CircuitBreakerState.HALF_OPEN:
                    self.state = CircuitBreakerState.CLOSED
                    self.failure_count = 0
                    self._half_open_probe_in_flight = False
                    _LOGGER.info("Circuit breaker recovered from HALF_OPEN to CLOSED")
                elif self.state == CircuitBreakerState.CLOSED:
                    self.failure_count = 0

            return result

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics (thread-safe snapshot)."""
        if self._lock.locked():
            return {"state": self.state, "note": "lock held, stats may be stale"}
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "timeout": self.timeout,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
            "half_open_start_time": self.half_open_start_time,
            "half_open_probe_in_flight": self._half_open_probe_in_flight,
        }

    async def reset(self) -> None:
        """Manually reset the circuit breaker."""
        async with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0.0
            self.half_open_start_time = 0.0
            self._half_open_probe_in_flight = False
        _LOGGER.info("Circuit breaker manually reset to CLOSED state")


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
