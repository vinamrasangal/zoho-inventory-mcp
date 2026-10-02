from __future__ import annotations

import httpx

from .auth import FileTokenStore, OAuthManager, TokenStore
from .client import ZohoInventoryClient
from .clock import Clock, SystemClock
from .config import Settings
from .rate_limit import RateLimiter
from .service import InventoryService


def build_service(
    settings: Settings | None = None,
    *,
    http: httpx.AsyncClient | None = None,
    store: TokenStore | None = None,
    clock: Clock | None = None,
) -> InventoryService:
    """Wire the connector together. Tests inject an in-process transport, a memory store and a fake clock."""
    settings = settings or Settings()
    clock = clock or SystemClock()
    http = http or httpx.AsyncClient(headers={"User-Agent": "zoho-inventory-mcp/0.1"})
    oauth = OAuthManager(settings, store or FileTokenStore(settings.token_path), http, clock)
    limiter = RateLimiter(
        settings.rate_limit_per_minute, settings.max_concurrency, settings.daily_request_budget, clock
    )
    return InventoryService(ZohoInventoryClient(settings, oauth, limiter, http, clock))
