from __future__ import annotations

import logging
import random
from typing import Any

import httpx

from .auth import OAuthManager
from .clock import Clock, SystemClock
from .config import Settings
from .errors import (
    ConfigurationError,
    InvalidRequest,
    NotFound,
    PermissionDenied,
    RateLimited,
    ZohoError,
    ZohoUnavailable,
)
from .rate_limit import RateLimiter

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {500, 502, 503, 504}


def _retry_after(resp: httpx.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


class ZohoInventoryClient:
    """Async HTTP client for the Zoho Inventory v1 API.

    Every request goes through the shared rate limiter, carries a fresh OAuth token and the
    organization ID, and is retried with exponential backoff and full jitter on 429/5xx/network
    errors. A 401 triggers one token refresh before giving up.
    """

    def __init__(
        self,
        settings: Settings,
        oauth: OAuthManager,
        limiter: RateLimiter,
        http: httpx.AsyncClient,
        clock: Clock | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.oauth = oauth
        self.limiter = limiter
        self.http = http
        self.clock = clock or SystemClock()
        self.rng = rng or random.Random()

    def _backoff(self, attempt: int) -> float:
        ceiling = min(self.settings.backoff_max_seconds, self.settings.backoff_base_seconds * 2**attempt)
        return self.rng.uniform(0, ceiling)

    async def get(
        self, path: str, params: dict[str, Any] | None = None, *, org_scoped: bool = True
    ) -> dict[str, Any]:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        if org_scoped:
            if not self.settings.organization_id:
                raise ConfigurationError(
                    "ZOHO_ORGANIZATION_ID is not set. Run `zoho-inventory-mcp orgs` to find it."
                )
            query["organization_id"] = self.settings.organization_id

        refreshed = False
        max_retries = self.settings.max_retries
        attempt = 0
        while True:
            tokens = await self.oauth.get_tokens()
            url = f"{self.settings.resolved_api_url(tokens.api_domain)}/inventory/v1{path}"
            headers = {"Authorization": f"Zoho-oauthtoken {tokens.access_token}"}
            try:
                async with self.limiter.slot():
                    resp = await self.http.get(
                        url, params=query, headers=headers, timeout=self.settings.request_timeout_seconds
                    )
            except httpx.TransportError as exc:
                if attempt >= max_retries:
                    raise ZohoUnavailable(f"Network error talking to Zoho: {exc}") from exc
                delay = self._backoff(attempt)
                log.warning("network error on %s (%s); retrying in %.2fs", path, exc, delay)
                await self.clock.sleep(delay)
                attempt += 1
                continue

            self.limiter.observe_headers(resp.headers)

            if resp.status_code == 401 and not refreshed:
                log.info("access token rejected; refreshing once")
                self.oauth.invalidate_access_token(tokens.access_token)
                refreshed = True
                continue

            if resp.status_code == 429 or resp.status_code in RETRYABLE_STATUS:
                retry_after = _retry_after(resp)
                if resp.status_code == 429:
                    self.limiter.cooldown(retry_after if retry_after is not None else self._backoff(attempt))
                if attempt >= max_retries:
                    raise self._error(resp)
                delay = retry_after if retry_after is not None else self._backoff(attempt)
                log.warning(
                    "Zoho returned %s on %s; retry %d/%d in %.2fs",
                    resp.status_code,
                    path,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                await self.clock.sleep(delay)
                attempt += 1
                continue

            body = self._json(resp)
            if resp.status_code >= 400 or body.get("code", 0) != 0:
                raise self._error(resp, body)
            return body

    @staticmethod
    def _json(resp: httpx.Response) -> dict[str, Any]:
        try:
            body = resp.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    def _error(self, resp: httpx.Response, body: dict[str, Any] | None = None) -> ZohoError:
        body = body if body is not None else self._json(resp)
        status, code = resp.status_code, body.get("code")
        message = body.get("message") or f"Zoho returned HTTP {status}."
        kwargs = {"status": status, "code": code}
        if status == 429:
            return RateLimited(f"Rate limited by Zoho: {message}", retry_after=_retry_after(resp), **kwargs)
        if status in (401, 403):
            return PermissionDenied(f"Not authorized: {message}", **kwargs)
        if status == 404:
            return NotFound(message, **kwargs)
        if status >= 500:
            return ZohoUnavailable(f"Zoho server error: {message}", **kwargs)
        return InvalidRequest(message, **kwargs)

    async def fetch_all(
        self,
        path: str,
        key: str,
        params: dict[str, Any] | None = None,
        *,
        per_page: int = 200,
        max_pages: int = 10,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Collect records across pages, stopping at `max_pages` to bound API usage.

        Returns the records and whether the scan was truncated (more pages existed).
        """
        records: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            body = await self.get(path, {**(params or {}), "page": page, "per_page": per_page})
            records.extend(body.get(key, []))
            if not body.get("page_context", {}).get("has_more_page"):
                return records, False
        return records, True
