from __future__ import annotations

import asyncio

import pytest

from zoho_inventory_mcp.errors import DailyBudgetExceeded
from zoho_inventory_mcp.rate_limit import RateLimiter


async def test_sliding_window_never_exceeds_limit_in_any_rolling_minute(clock):
    limiter = RateLimiter(per_minute=10, max_concurrency=10, clock=clock)
    sent: list[float] = []
    for i in range(35):
        async with limiter.slot():
            sent.append(clock.now)
        clock.now += 1.5 if i % 3 else 0.0
    for t in sent:
        assert sum(1 for s in sent if t <= s < t + 60) <= 10


async def test_waits_for_oldest_request_to_leave_the_window(clock):
    limiter = RateLimiter(per_minute=3, max_concurrency=10, clock=clock)
    for _ in range(3):
        async with limiter.slot():
            clock.now += 10
    async with limiter.slot():
        pass
    assert clock.sleeps == [pytest.approx(30.0)]


async def test_concurrency_is_capped(clock):
    limiter = RateLimiter(per_minute=1000, max_concurrency=2, clock=clock)
    in_flight = peak = 0

    async def call() -> None:
        nonlocal in_flight, peak
        async with limiter.slot():
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*(call() for _ in range(8)))
    assert peak == 2


async def test_cooldown_pauses_all_callers(clock):
    limiter = RateLimiter(per_minute=100, max_concurrency=5, clock=clock)
    limiter.cooldown(5)
    async with limiter.slot():
        pass
    assert clock.sleeps == [5]


async def test_daily_budget(clock):
    limiter = RateLimiter(per_minute=100, max_concurrency=5, daily_budget=1, clock=clock)
    async with limiter.slot():
        pass
    with pytest.raises(DailyBudgetExceeded):
        async with limiter.slot():
            pass
    clock.now += 86400
    async with limiter.slot():
        pass


def test_quota_headers_are_parsed(clock):
    limiter = RateLimiter(per_minute=100, max_concurrency=5, clock=clock)
    limiter.observe_headers({"X-Rate-Limit-Limit": "1000", "X-Rate-Limit-Remaining": "42"})
    snapshot = limiter.snapshot()
    assert snapshot["zoho_daily_limit"] == 1000
    assert snapshot["zoho_daily_remaining"] == 42
