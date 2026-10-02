from __future__ import annotations

import asyncio
import socket
import stat
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from zoho_inventory_mcp.auth import FileTokenStore, TokenSet
from zoho_inventory_mcp.auth.login_flow import interactive_login
from zoho_inventory_mcp.errors import AuthenticationRequired

from .conftest import MOCK_URL


def test_authorization_url_requests_offline_read_only_access(harness):
    url = urlparse(harness.service.client.oauth.authorization_url("xyz"))
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert f"{url.scheme}://{url.netloc}{url.path}" == f"{MOCK_URL}/oauth/v2/auth"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["state"] == "xyz"
    assert all(scope.endswith(".READ") for scope in query["scope"].split(","))


async def test_authorization_code_flow_end_to_end(make_harness):
    h = make_harness(refresh_token=None)
    oauth = h.service.client.oauth

    consent = await h.http.get(oauth.authorization_url("state-123"))
    assert consent.status_code == 200 and "Accept" in consent.text

    approve_url = f"{MOCK_URL}/oauth/v2/auth/approve?{urlparse(oauth.authorization_url('state-123')).query}"
    redirect = await h.http.get(approve_url)
    assert redirect.status_code == 302
    params = {k: v[0] for k, v in parse_qs(urlparse(redirect.headers["location"]).query).items()}
    assert params["state"] == "state-123"

    tokens = await oauth.exchange_code(params["code"], accounts_server=params["accounts-server"])
    assert tokens.refresh_token and tokens.api_domain == MOCK_URL
    assert h.store.load() == tokens

    page = await h.service.list_items(per_page=5)
    assert len(page.results) == 5


async def test_authorization_code_is_single_use(make_harness):
    h = make_harness(refresh_token=None)
    oauth = h.service.client.oauth
    redirect = await h.http.get(
        f"{MOCK_URL}/oauth/v2/auth/approve?{urlparse(oauth.authorization_url('s')).query}"
    )
    code = parse_qs(urlparse(redirect.headers["location"]).query)["code"][0]
    await oauth.exchange_code(code)
    with pytest.raises(AuthenticationRequired, match="invalid_code"):
        await oauth.exchange_code(code)


async def test_no_credentials_raises_auth_required(make_harness):
    h = make_harness(refresh_token=None)
    with pytest.raises(AuthenticationRequired):
        await h.service.list_items()


async def test_expired_access_token_is_refreshed_proactively(harness):
    await harness.service.list_items()
    assert harness.state.tokens_issued == 1
    harness.clock.now += 3600
    await harness.service.list_items()
    assert harness.state.tokens_issued == 2
    assert harness.store.load().refresh_token == "mock-refresh-token"


async def test_parallel_calls_share_a_single_refresh(harness):
    await asyncio.gather(*(harness.service.list_items() for _ in range(10)))
    assert harness.state.tokens_issued == 1


async def test_rejected_token_triggers_one_refresh_and_retry(harness):
    await harness.service.list_items()
    harness.state.expire_all_access_tokens()
    page = await harness.service.list_items()
    assert page.results
    assert harness.state.tokens_issued == 2


async def test_invalid_refresh_token(make_harness):
    h = make_harness(refresh_token="revoked-token")
    with pytest.raises(AuthenticationRequired, match="invalid_code"):
        await h.service.list_items()


async def test_logout_revokes_refresh_token(harness):
    await harness.service.list_items()
    harness.store.save(harness.store.load().model_copy(update={"refresh_token": "mock-refresh-token"}))
    assert await harness.service.client.oauth.revoke()
    assert harness.store.load() is None
    assert "mock-refresh-token" not in harness.state.refresh_tokens


def test_file_token_store_is_private(tmp_path):
    store = FileTokenStore(tmp_path / "nested" / "tokens.json")
    tokens = TokenSet(access_token="a", refresh_token="r", expires_at=1.0)
    store.save(tokens)
    assert store.load() == tokens
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    store.clear()
    assert store.load() is None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("tamper_state", [False, True])
async def test_interactive_login_validates_state(make_harness, monkeypatch, tamper_state):
    port = _free_port()
    h = make_harness(refresh_token=None, redirect_uri=f"http://127.0.0.1:{port}/callback")
    h.state.codes["1000.testcode"] = {
        "scopes": ("ZohoInventory.items.READ",),
        "redirect_uri": f"http://127.0.0.1:{port}/callback",
        "expires_at": h.clock.time() + 60,
    }

    def fake_browser(url: str) -> bool:
        state = "forged" if tamper_state else parse_qs(urlparse(url).query)["state"][0]
        callback = f"http://127.0.0.1:{port}/callback?code=1000.testcode&state={state}"
        threading.Thread(target=httpx.get, args=(callback,), daemon=True).start()
        return True

    monkeypatch.setattr("webbrowser.open", fake_browser)
    if tamper_state:
        with pytest.raises(AuthenticationRequired, match="state mismatch"):
            await interactive_login(h.service.client.oauth, timeout_seconds=5)
    else:
        tokens = await interactive_login(h.service.client.oauth, timeout_seconds=5)
        assert tokens.refresh_token
