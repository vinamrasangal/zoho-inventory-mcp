from __future__ import annotations

import asyncio
import secrets
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ..errors import AuthenticationRequired, ConfigurationError
from .oauth import OAuthManager
from .token_store import TokenSet

_SUCCESS_PAGE = b"""<!doctype html><html><body style="font-family:sans-serif;padding:3rem">
<h2>Zoho Inventory connected.</h2><p>You can close this tab and return to the terminal.</p>
</body></html>"""


@dataclass
class CallbackResult:
    code: str | None = None
    state: str | None = None
    accounts_server: str | None = None
    error: str | None = None


def _make_handler(result: CallbackResult, done: threading.Event, path: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path != path:
                self.send_error(404)
                return
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            result.code = query.get("code")
            result.state = query.get("state")
            result.accounts_server = query.get("accounts-server")
            result.error = query.get("error")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(_SUCCESS_PAGE)
            done.set()

        def log_message(self, *args) -> None:
            pass

    return Handler


async def interactive_login(
    oauth: OAuthManager, *, open_browser: bool = True, timeout_seconds: float = 300
) -> TokenSet:
    """Run the browser consent flow, catching the redirect on a short-lived localhost server."""
    redirect = urlparse(oauth.settings.redirect_uri)
    if redirect.hostname not in {"localhost", "127.0.0.1"} or not redirect.port:
        raise ConfigurationError(
            "Interactive login needs ZOHO_REDIRECT_URI like http://localhost:8765/callback. "
            "For other setups use `auth exchange --code` with a Self Client code."
        )

    state = secrets.token_urlsafe(24)
    result, done = CallbackResult(), threading.Event()
    server = HTTPServer((redirect.hostname, redirect.port), _make_handler(result, done, redirect.path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = oauth.authorization_url(state)
        print(f"\nOpen this URL to connect Zoho Inventory:\n\n  {url}\n")
        if open_browser:
            webbrowser.open(url)
        finished = await asyncio.to_thread(done.wait, timeout_seconds)
    finally:
        server.shutdown()
        server.server_close()

    if not finished:
        raise AuthenticationRequired("Timed out waiting for the Zoho consent redirect.")
    if result.error:
        raise AuthenticationRequired(f"Zoho consent failed: {result.error}.")
    if not result.code or not secrets.compare_digest(result.state or "", state):
        raise AuthenticationRequired("OAuth state mismatch; the redirect was not from this login attempt.")
    return await oauth.exchange_code(result.code, accounts_server=result.accounts_server)
