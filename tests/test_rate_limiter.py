"""Tests for the token-bucket rate limiter."""

import asyncio

import pytest

from violet_poolcontroller_api.utils_rate_limiter import RateLimiter


async def test_waiters_are_released_by_priority() -> None:
    limiter = RateLimiter(max_requests=1, time_window=0.02, burst_size=0, retry_after=0.01)
    assert await limiter.acquire(priority=3)
    completed: list[str] = []

    async def wait(label: str, priority: int) -> None:
        await limiter.wait_if_needed(priority=priority, timeout=1)
        completed.append(label)

    low = asyncio.create_task(wait("low", 4))
    await asyncio.sleep(0)
    critical = asyncio.create_task(wait("critical", 1))
    await asyncio.gather(low, critical)

    assert completed == ["critical", "low"]


async def test_stats_reads_have_no_request_side_effect() -> None:
    limiter = RateLimiter()
    limiter._recent_stats["requests_last_minute"] = 4
    limiter._recent_stats["last_minute_reset"] -= 61
    snapshot = dict(limiter._recent_stats)
    before = limiter.get_stats()
    after = limiter.get_stats()

    assert before["total_requests"] == 0
    assert after["total_requests"] == 0
    assert before["recent_requests_1min"] == after["recent_requests_1min"] == 0
    assert limiter._recent_stats == snapshot


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_requests": 0}, "max_requests"),
        ({"time_window": 0}, "time_window"),
        ({"burst_size": -1}, "burst_size"),
        ({"retry_after": 0}, "retry_after"),
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        RateLimiter(**kwargs)
