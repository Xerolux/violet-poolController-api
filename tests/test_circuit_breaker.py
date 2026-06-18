"""Tests for violet_poolcontroller_api.circuit_breaker module.

These tests exercise the real async ``CircuitBreaker`` API: state transitions
happen inside ``await cb.call(func)``, driven by the success/failure of the
wrapped coroutine. There are no public ``record_failure``/``can_attempt``
methods.
"""

import pytest

from violet_poolcontroller_api.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerState,
)


class _IgnoredError(Exception):
    """Deterministic error that should bypass the failure counter."""


def test_initial_state_is_closed():
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


async def test_successful_call_returns_result_and_stays_closed():
    cb = CircuitBreaker(failure_threshold=3)

    async def ok():
        return 42

    assert await cb.call(ok) == 42
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


async def test_call_passes_args_and_kwargs():
    cb = CircuitBreaker()

    async def add(a, b, *, c):
        return a + b + c

    assert await cb.call(add, 1, 2, c=3) == 6


async def test_opens_after_threshold_failures():
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(fail)

    assert cb.state == CircuitBreakerState.OPEN
    assert cb.failure_count == 3


async def test_custom_threshold_honoured():
    cb = CircuitBreaker(failure_threshold=5, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(4):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    # Not yet open at threshold-1
    assert cb.state == CircuitBreakerState.CLOSED
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN


async def test_call_raises_when_open():
    cb = CircuitBreaker(failure_threshold=1, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(ok)


async def test_success_resets_failure_count_below_threshold():
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.failure_count == 2
    assert cb.state == CircuitBreakerState.CLOSED

    assert await cb.call(ok) == "ok"
    assert cb.failure_count == 0
    assert cb.state == CircuitBreakerState.CLOSED


async def test_recovers_from_open_to_half_open_to_closed():
    cb = CircuitBreaker(failure_threshold=2, timeout=1.0, recovery_timeout=300.0)

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN

    # Simulate the open timeout having elapsed.
    cb.last_failure_time -= 2.0

    # The call transitions OPEN -> HALF_OPEN, then on success -> CLOSED.
    assert await cb.call(ok) == "ok"
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


async def test_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=2, timeout=1.0)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN

    cb.last_failure_time -= 2.0  # force HALF_OPEN on next call

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN


async def test_ignored_exceptions_do_not_count_as_failures():
    cb = CircuitBreaker(failure_threshold=2, ignored_exceptions=(_IgnoredError,))

    async def fail_ignored():
        raise _IgnoredError("ignore me")

    with pytest.raises(_IgnoredError):
        await cb.call(fail_ignored)

    assert cb.failure_count == 0
    assert cb.state == CircuitBreakerState.CLOSED


async def test_rapid_failures_keep_circuit_open():
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    for _ in range(10):
        with pytest.raises((RuntimeError, CircuitBreakerOpenError)):
            await cb.call(fail)

    assert cb.state == CircuitBreakerState.OPEN


async def test_alternating_success_failure_stays_closed():
    cb = CircuitBreaker(failure_threshold=3, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    for i in range(5):
        if i % 2 == 0:
            with pytest.raises(RuntimeError):
                await cb.call(fail)
        else:
            await cb.call(ok)

    assert cb.state == CircuitBreakerState.CLOSED


def test_get_stats_returns_expected_fields():
    cb = CircuitBreaker(failure_threshold=3, timeout=10.0, recovery_timeout=20.0)
    stats = cb.get_stats()
    assert stats["state"] == CircuitBreakerState.CLOSED
    assert stats["failure_count"] == 0
    assert stats["failure_threshold"] == 3
    assert stats["timeout"] == 10.0
    assert stats["recovery_timeout"] == 20.0
    assert "last_failure_time" in stats
    assert "half_open_start_time" in stats


async def test_manual_reset_returns_to_closed():
    cb = CircuitBreaker(failure_threshold=1, timeout=60.0)

    async def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitBreakerState.OPEN

    await cb.reset()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0
