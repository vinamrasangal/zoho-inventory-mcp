"""Retries, backoff and rate limiting against the mock Zoho server."""

from __future__ import annotations

import asyncio

import pytest

from zoho_inventory_mcp.errors import (
    ConfigurationError,
    DailyBudgetExceeded,
    RateLimited,
    ZohoUnavailable,
)


async def test_429_is_retried_after_retry_after(harness):
    harness.state.fail_next(429)
    page = await harness.service.list_items()
    assert page.results
    assert 1.0 in harness.clock.sleeps


async def test_5xx_is_retried_with_backoff(harness):
    harness.state.fail_next(503, 502)
    page = await harness.service.list_items()
    assert page.results
    assert len(harness.clock.sleeps) == 2


async def test_gives_up_after_max_retries(make_harness):
    h = make_harness(max_retries=2)
    h.state.fail_next(503, 503, 503, 503)
    with pytest.raises(ZohoUnavailable):
        await h.service.list_items()
    assert h.state.api_calls == 3


async def test_persistent_429_surfaces_retry_hint(make_harness):
    h = make_harness(max_retries=1)
    h.state.fail_next(429, 429)
    with pytest.raises(RateLimited) as exc_info:
        await h.service.list_items()
    assert "Wait" in exc_info.value.for_agent()


async def test_backoff_is_bounded(make_harness):
    h = make_harness(max_retries=6, backoff_base_seconds=1, backoff_max_seconds=4)
    h.state.fail_next(*[500] * 6)
    await h.service.list_items()
    assert all(0 <= s <= 4 for s in h.clock.sleeps)


async def test_recovers_when_server_limit_is_lower_than_client_limit(make_harness):
    # Client believes it may send 100/min, but the organization is only allowed 5/min.
    h = make_harness(mock={"rate_limit_per_minute": 5}, max_retries=10)
    for _ in range(12):
        await h.service.get_item(item_id="240000000000001")
    assert h.state.throttled > 0
    assert h.state.api_calls == 12


async def test_client_side_limiter_avoids_429s_entirely(make_harness):
    h = make_harness(mock={"rate_limit_per_minute": 5}, rate_limit_per_minute=5)
    await asyncio.gather(*(h.service.get_item(item_id="240000000000001") for _ in range(12)))
    assert h.state.throttled == 0
    assert h.state.api_calls == 12
    assert h.clock.now - 1_790_000_000.0 >= 60  # 12 calls at 5/min needs more than a minute


async def test_daily_budget_stops_calls_before_they_are_sent(make_harness):
    h = make_harness(daily_request_budget=2)
    await h.service.list_items()
    await h.service.list_items()
    with pytest.raises(DailyBudgetExceeded):
        await h.service.list_items()
    assert h.state.api_calls == 2


async def test_zoho_reported_quota_exhaustion_is_respected(make_harness):
    h = make_harness(mock={"daily_limit": 2})
    await h.service.list_items()
    await h.service.list_items()
    with pytest.raises(DailyBudgetExceeded, match="quota"):
        await h.service.list_items()


async def test_missing_organization_id_is_a_configuration_error(make_harness):
    h = make_harness(organization_id=None)
    with pytest.raises(ConfigurationError, match="ZOHO_ORGANIZATION_ID"):
        await h.service.list_items()
