from __future__ import annotations

import asyncio
import datetime as dt
from collections import deque
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .clock import Clock, SystemClock
from .errors import DailyBudgetExceeded

WINDOW_SECONDS = 60.0


@dataclass
class ZohoQuota:
    """Daily quota as reported by Zoho's X-Rate-Limit-* response headers, when present."""

    limit: int | None = None
    remaining: int | None = None
    reset_seconds: int | None = None


class RateLimiter:
    """Client-side throttle that keeps the connector inside Zoho's limits.

    Three layers, all shared by every tool call in the process:
      * a sliding 60-second window for the per-minute limit (Zoho: 100 requests/min per
        organization). A token bucket refilling at N/60 per second would allow up to 2N requests
        in some rolling minute, which still trips Zoho's limiter,
      * a semaphore for the concurrent-request limit (lowest Zoho plans allow 5 in flight),
      * an optional daily budget so one agent cannot drain the plan quota that the merchant's
        other integrations depend on.
    A 429 from Zoho puts the whole limiter into a cooldown, so parallel calls back off together
    instead of each one hammering the API.
    """

    def __init__(
        self,
        per_minute: int,
        max_concurrency: int,
        daily_budget: int | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.clock = clock or SystemClock()
        self.per_minute = per_minute
        self.max_concurrency = max_concurrency
        self.daily_budget = daily_budget
        self.quota = ZohoQuota()
        self._sent: deque[float] = deque()
        self._cooldown_until = 0.0
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._lock = asyncio.Lock()
        self._day = self._today()
        self._used_today = 0

    def _today(self) -> dt.date:
        return dt.datetime.fromtimestamp(self.clock.time()).date()

    def _expire(self, now: float) -> None:
        while self._sent and self._sent[0] <= now - WINDOW_SECONDS:
            self._sent.popleft()

    def _check_daily_budget(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._used_today = today, 0
        if self.daily_budget is not None and self._used_today >= self.daily_budget:
            raise DailyBudgetExceeded(f"Daily budget of {self.daily_budget} Zoho API requests reached.")
        if self.quota.remaining is not None and self.quota.remaining <= 0:
            raise DailyBudgetExceeded("Zoho reports the organization's daily API quota is exhausted.")

    async def _take_token(self) -> None:
        async with self._lock:
            self._check_daily_budget()
            while True:
                now = self.clock.monotonic()
                if now < self._cooldown_until:
                    await self.clock.sleep(self._cooldown_until - now)
                    continue
                self._expire(now)
                if len(self._sent) < self.per_minute:
                    self._sent.append(now)
                    self._used_today += 1
                    return
                await self.clock.sleep(self._sent[0] + WINDOW_SECONDS - now)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        """Wait for permission to send one request."""
        async with self._semaphore:
            await self._take_token()
            yield

    def cooldown(self, seconds: float) -> None:
        self._cooldown_until = max(self._cooldown_until, self.clock.monotonic() + seconds)

    def observe_headers(self, headers: Mapping[str, str]) -> None:
        def as_int(name: str) -> int | None:
            value = headers.get(name)
            return int(value) if value is not None and value.lstrip("-").isdigit() else None

        limit, remaining = as_int("X-Rate-Limit-Limit"), as_int("X-Rate-Limit-Remaining")
        if limit is not None or remaining is not None:
            self.quota = ZohoQuota(limit, remaining, as_int("X-Rate-Limit-Reset"))

    def snapshot(self) -> dict[str, object]:
        self._expire(self.clock.monotonic())
        return {
            "per_minute_limit": self.per_minute,
            "requests_left_this_minute": self.per_minute - len(self._sent),
            "max_concurrency": self.max_concurrency,
            "requests_sent_today": self._used_today,
            "daily_budget": self.daily_budget,
            "zoho_daily_limit": self.quota.limit,
            "zoho_daily_remaining": self.quota.remaining,
            "cooling_down_seconds": round(max(0.0, self._cooldown_until - self.clock.monotonic()), 1),
        }
