from __future__ import annotations

import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def time(self) -> float: ...
    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def time(self) -> float:
        return time.time()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
