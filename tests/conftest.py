from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from mock_zoho import MockConfig, MockState, create_app
from mock_zoho.data import ORG_ID
from zoho_inventory_mcp.auth import MemoryTokenStore
from zoho_inventory_mcp.config import Settings
from zoho_inventory_mcp.factory import build_service
from zoho_inventory_mcp.service import InventoryService

MOCK_URL = "http://mock.zoho"


@dataclass
class FakeClock:
    """Shared by the connector and the mock server so backoff and rate windows run instantly."""

    now: float = 1_790_000_000.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


@dataclass
class Harness:
    service: InventoryService
    state: MockState
    clock: FakeClock
    store: MemoryTokenStore
    http: httpx.AsyncClient


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "client_id": "mock-client-id",
        "client_secret": "mock-client-secret",
        "accounts_url": MOCK_URL,
        "organization_id": ORG_ID,
        "refresh_token": "mock-refresh-token",
        "redirect_uri": "http://localhost:8765/callback",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def make_harness(clock: FakeClock) -> AsyncIterator[Callable[..., Harness]]:
    clients: list[httpx.AsyncClient] = []

    def factory(mock: dict[str, Any] | None = None, **settings: Any) -> Harness:
        app = create_app(MockConfig(base_url=MOCK_URL, clock=clock.time, **(mock or {})))
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
        clients.append(http)
        store = MemoryTokenStore()
        service = build_service(make_settings(**settings), http=http, store=store, clock=clock)
        return Harness(service, app.state.mock, clock, store, http)

    yield factory
    for http in clients:
        await http.aclose()


@pytest.fixture
def harness(make_harness: Callable[..., Harness]) -> Harness:
    return make_harness()
