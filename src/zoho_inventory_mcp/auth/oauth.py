from __future__ import annotations

import asyncio
from urllib.parse import urlencode

import httpx

from ..clock import Clock, SystemClock
from ..config import Settings
from ..errors import AuthenticationRequired, ConfigurationError, ZohoUnavailable
from .token_store import TokenSet, TokenStore


class OAuthManager:
    """Zoho OAuth 2.0 (authorization-code grant with offline access).

    Owns the token lifecycle: builds the consent URL, exchanges the code, refreshes access tokens
    (they live for one hour) and revokes on logout. Refreshes are single-flight so a burst of
    parallel tool calls triggers exactly one refresh.
    """

    def __init__(
        self, settings: Settings, store: TokenStore, http: httpx.AsyncClient, clock: Clock | None = None
    ) -> None:
        self.settings = settings
        self.store = store
        self.http = http
        self.clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._tokens: TokenSet | None = None

    def _client_credentials(self) -> tuple[str, str]:
        s = self.settings
        if not s.client_id or not s.client_secret:
            raise ConfigurationError("ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET must be set.")
        return s.client_id, s.client_secret.get_secret_value()

    def authorization_url(self, state: str) -> str:
        client_id, _ = self._client_credentials()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "scope": ",".join(self.settings.scopes),
                "redirect_uri": self.settings.redirect_uri,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{self.settings.resolved_accounts_url}/oauth/v2/auth?{query}"

    async def _token_request(self, accounts_url: str, data: dict[str, str]) -> dict:
        try:
            resp = await self.http.post(f"{accounts_url.rstrip('/')}/oauth/v2/token", data=data)
        except httpx.HTTPError as exc:
            raise ZohoUnavailable(f"Could not reach Zoho accounts server: {exc}") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        # Zoho reports OAuth failures as HTTP 200 with an "error" field.
        if resp.status_code >= 400 or "error" in body or "access_token" not in body:
            error = body.get("error", f"HTTP {resp.status_code}")
            raise AuthenticationRequired(f"Zoho rejected the token request ({error}).")
        return body

    def _to_tokens(self, body: dict, accounts_url: str, refresh_token: str | None) -> TokenSet:
        return TokenSet(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_at=self.clock.time() + float(body.get("expires_in", 3600)),
            api_domain=body.get("api_domain"),
            accounts_server=accounts_url,
            scope=body.get("scope"),
        )

    async def exchange_code(self, code: str, accounts_server: str | None = None) -> TokenSet:
        """Exchange an authorization code. `accounts_server` comes from the redirect for multi-DC accounts."""
        client_id, client_secret = self._client_credentials()
        accounts_url = accounts_server or self.settings.resolved_accounts_url
        body = await self._token_request(
            accounts_url,
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": self.settings.redirect_uri,
            },
        )
        if not body.get("refresh_token"):
            raise AuthenticationRequired(
                "Zoho did not return a refresh token. Remove the app's existing grant and log in again."
            )
        tokens = self._to_tokens(body, accounts_url, None)
        self.store.save(tokens)
        self._tokens = tokens
        return tokens

    async def _refresh(self, refresh_token: str, accounts_url: str, api_domain: str | None) -> TokenSet:
        client_id, client_secret = self._client_credentials()
        body = await self._token_request(
            accounts_url,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        tokens = self._to_tokens(body, accounts_url, refresh_token)
        if tokens.api_domain is None:
            tokens.api_domain = api_domain
        self.store.save(tokens)
        return tokens

    def current_tokens(self) -> TokenSet | None:
        if self._tokens is None:
            self._tokens = self.store.load()
        return self._tokens

    async def get_access_token(self) -> str:
        return (await self.get_tokens()).access_token

    async def get_tokens(self) -> TokenSet:
        tokens = self.current_tokens()
        if tokens and not tokens.is_expired(self.clock.time()):
            return tokens
        async with self._lock:
            tokens = self.current_tokens()
            if tokens and not tokens.is_expired(self.clock.time()):
                return tokens
            if tokens and tokens.refresh_token:
                refresh_token = tokens.refresh_token
                accounts_url = tokens.accounts_server or self.settings.resolved_accounts_url
                api_domain = tokens.api_domain
            elif self.settings.refresh_token:
                refresh_token = self.settings.refresh_token.get_secret_value()
                accounts_url, api_domain = self.settings.resolved_accounts_url, None
            else:
                raise AuthenticationRequired("No Zoho credentials found.")
            self._tokens = await self._refresh(refresh_token, accounts_url, api_domain)
            return self._tokens

    def invalidate_access_token(self, rejected_token: str) -> None:
        """Mark the access token as expired after Zoho rejected it (revoked or rotated early)."""
        tokens = self.current_tokens()
        if tokens and tokens.access_token == rejected_token:
            self._tokens = tokens.model_copy(update={"expires_at": 0.0})

    async def revoke(self) -> bool:
        tokens = self.current_tokens()
        revoked = False
        if tokens and tokens.refresh_token:
            accounts_url = tokens.accounts_server or self.settings.resolved_accounts_url
            try:
                resp = await self.http.post(
                    f"{accounts_url}/oauth/v2/token/revoke", data={"token": tokens.refresh_token}
                )
                revoked = resp.status_code < 400
            except httpx.HTTPError:
                revoked = False
        self.store.clear()
        self._tokens = None
        return revoked
