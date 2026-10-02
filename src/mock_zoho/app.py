"""A local stand-in for Zoho's accounts server and Inventory v1 API.

Mirrors the parts of Zoho the connector relies on: the OAuth authorization-code and refresh flows
(including Zoho's habit of returning OAuth errors as HTTP 200), `organization_id` scoping, OAuth
scope checks, `page_context` pagination, per-minute rate limiting with 429s, the daily
X-Rate-Limit-* headers, and injectable failures for testing retries.
"""

from __future__ import annotations

import html
import math
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from .data import Dataset, build_dataset

DEFAULT_SCOPES = (
    "ZohoInventory.items.READ",
    "ZohoInventory.salesorders.READ",
    "ZohoInventory.contacts.READ",
    "ZohoInventory.settings.READ",
)


@dataclass
class MockConfig:
    base_url: str = "http://localhost:8800"
    client_id: str = "mock-client-id"
    client_secret: str = "mock-client-secret"
    token_ttl_seconds: int = 3600
    rate_limit_per_minute: int = 100
    daily_limit: int = 1000
    self_client_refresh_token: str = "mock-refresh-token"
    clock: Callable[[], float] = time.time


@dataclass
class MockState:
    config: MockConfig
    data: Dataset = field(default_factory=build_dataset)
    codes: dict[str, dict[str, Any]] = field(default_factory=dict)
    refresh_tokens: dict[str, tuple[str, ...]] = field(default_factory=dict)
    access_tokens: dict[str, tuple[float, tuple[str, ...]]] = field(default_factory=dict)
    window: deque[float] = field(default_factory=deque)
    daily_used: int = 0
    forced_failures: deque[int] = field(default_factory=deque)
    api_calls: int = 0
    throttled: int = 0
    tokens_issued: int = 0

    def __post_init__(self) -> None:
        self.refresh_tokens[self.config.self_client_refresh_token] = DEFAULT_SCOPES

    def fail_next(self, *statuses: int) -> None:
        self.forced_failures.extend(statuses)

    def expire_all_access_tokens(self) -> None:
        self.access_tokens.clear()


def _zoho_error(status: int, code: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status, headers=headers)


def _paginate(
    records: list[dict[str, Any]], request: Request, key: str, report: str, applied_filter: str
) -> dict[str, Any]:
    q = request.query_params
    page = max(1, int(q.get("page", 1)))
    per_page = min(200, max(1, int(q.get("per_page", 200))))
    chunk = records[(page - 1) * per_page : page * per_page]
    return {
        "code": 0,
        "message": "success",
        key: chunk,
        "page_context": {
            "page": page,
            "per_page": per_page,
            "has_more_page": page * per_page < len(records),
            "report_name": report,
            "applied_filter": applied_filter,
            "sort_column": q.get("sort_column", "created_time"),
            "sort_order": q.get("sort_order", "D"),
        },
    }


def _status_filter(q: Any, default: str) -> str:
    return q.get("filter_by", default).removeprefix("Status.").lower()


def _matches(text: str | None, *fields: Any) -> bool:
    if not text:
        return True
    needle = text.lower()
    return any(needle in str(f or "").lower() for f in fields)


def create_app(config: MockConfig | None = None) -> Starlette:
    config = config or MockConfig()
    state = MockState(config)

    async def params(request: Request) -> dict[str, str]:
        merged = dict(request.query_params)
        if request.method == "POST":
            merged.update({k: str(v) for k, v in (await request.form()).items()})
        return merged

    # OAuth

    async def authorize(request: Request) -> Response:
        q = request.query_params
        if q.get("client_id") != config.client_id:
            return HTMLResponse("<h3>Invalid client_id</h3>", status_code=400)
        approve = html.escape(f"/oauth/v2/auth/approve?{urlencode(dict(q))}")
        scopes = html.escape(q.get("scope", "").replace(",", ", "))
        org = html.escape(state.data.organizations[0]["name"])
        button = "padding:.6rem 1.2rem;background:#e42527;color:#fff;text-decoration:none;border-radius:4px"
        return HTMLResponse(
            '<!doctype html><html><body style="font-family:sans-serif;padding:3rem;max-width:40rem">'
            "<h2>Mock Zoho Accounts</h2>"
            f"<p><b>zoho-inventory-mcp</b> would like to access <b>{org}</b>:</p>"
            f"<p><code>{scopes}</code></p>"
            f'<p><a href="{approve}" style="{button}">Accept</a></p></body></html>'
        )

    async def approve(request: Request) -> Response:
        q = request.query_params
        code = f"1000.{secrets.token_hex(16)}"
        scopes = tuple(s for s in q.get("scope", "").split(",") if s)
        state.codes[code] = {
            "scopes": scopes,
            "redirect_uri": q.get("redirect_uri"),
            "expires_at": config.clock() + 120,
        }
        query = {"code": code, "location": "in", "accounts-server": config.base_url}
        if q.get("state"):
            query["state"] = q["state"]
        return RedirectResponse(f"{q.get('redirect_uri')}?{urlencode(query)}", status_code=302)

    def issue_access_token(scopes: tuple[str, ...]) -> dict[str, Any]:
        token = f"1000.{secrets.token_hex(16)}"
        state.tokens_issued += 1
        state.access_tokens[token] = (config.clock() + config.token_ttl_seconds, scopes)
        return {
            "access_token": token,
            "api_domain": config.base_url,
            "token_type": "Bearer",
            "expires_in": config.token_ttl_seconds,
            "scope": " ".join(scopes),
        }

    async def token(request: Request) -> Response:
        p = await params(request)
        if p.get("client_id") != config.client_id or p.get("client_secret") != config.client_secret:
            return JSONResponse({"error": "invalid_client"})
        grant = p.get("grant_type")
        if grant == "authorization_code":
            entry = state.codes.pop(p.get("code", ""), None)
            if not entry or entry["expires_at"] < config.clock():
                return JSONResponse({"error": "invalid_code"})
            if entry["redirect_uri"] != p.get("redirect_uri"):
                return JSONResponse({"error": "invalid_redirect_uri"})
            refresh = f"1000.{secrets.token_hex(24)}"
            state.refresh_tokens[refresh] = entry["scopes"]
            return JSONResponse({**issue_access_token(entry["scopes"]), "refresh_token": refresh})
        if grant == "refresh_token":
            scopes = state.refresh_tokens.get(p.get("refresh_token", ""))
            if scopes is None:
                return JSONResponse({"error": "invalid_code"})
            return JSONResponse(issue_access_token(scopes))
        return JSONResponse({"error": "unsupported_grant_type"})

    async def revoke(request: Request) -> Response:
        state.refresh_tokens.pop((await params(request)).get("token", ""), None)
        return JSONResponse({"status": "success"})

    # API guard

    def guard(request: Request, scope: str, org_scoped: bool = True) -> tuple[JSONResponse | None, dict]:
        now = config.clock()
        auth = request.headers.get("Authorization", "")
        token_value = auth.removeprefix("Zoho-oauthtoken ").strip()
        entry = state.access_tokens.get(token_value)
        if not auth.startswith("Zoho-oauthtoken ") or entry is None or entry[0] <= now:
            return _zoho_error(401, 57, "You are not authorized to perform this operation"), {}
        granted = entry[1]
        if (
            scope not in granted
            and scope.replace(".READ", ".ALL") not in granted
            and "ZohoInventory.FullAccess.all" not in granted
        ):
            return _zoho_error(401, 57, f"OAuth scope {scope} is required for this operation"), {}

        while state.window and state.window[0] <= now - 60:
            state.window.popleft()
        if len(state.window) >= config.rate_limit_per_minute:
            state.throttled += 1
            retry_after = max(1, math.ceil(state.window[0] + 60 - now))
            return _zoho_error(
                429,
                44,
                "You have made too many requests. Please try again after some time.",
                {"Retry-After": str(retry_after)},
            ), {}
        state.window.append(now)
        state.daily_used += 1
        state.api_calls += 1
        headers = {
            "X-Rate-Limit-Limit": str(config.daily_limit),
            "X-Rate-Limit-Remaining": str(max(0, config.daily_limit - state.daily_used)),
            "X-Rate-Limit-Reset": str(int(86400 - now % 86400)),
        }

        if state.forced_failures:
            status = state.forced_failures.popleft()
            extra = {"Retry-After": "1"} if status == 429 else {}
            return _zoho_error(status, 44 if status == 429 else 500, "Injected failure", headers | extra), {}
        if (
            org_scoped
            and request.query_params.get("organization_id") != state.data.organizations[0]["organization_id"]
        ):
            return _zoho_error(400, 6041, "Invalid value passed for organization_id", headers), {}
        return None, headers

    def ok(body: dict[str, Any], headers: dict[str, str]) -> JSONResponse:
        return JSONResponse(body, headers=headers)

    async def organizations(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.settings.READ", org_scoped=False)
        return err or ok(
            {"code": 0, "message": "success", "organizations": state.data.organizations}, headers
        )

    async def list_items(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.items.READ")
        if err:
            return err
        q = request.query_params
        status = _status_filter(q, "Status.All")
        records = [
            {k: v for k, v in item.items() if k != "warehouses"}
            for item in state.data.items.values()
            if (status == "all" or item["status"] == status)
            and _matches(q.get("search_text"), item["name"], item["sku"], item["description"])
            and (not q.get("sku") or item["sku"].lower() == q["sku"].lower())
        ]
        sort_column = q.get("sort_column", "name")
        if sort_column in {"name", "sku", "rate", "stock_on_hand"}:
            records.sort(key=lambda r: r[sort_column])
        return ok(_paginate(records, request, "items", "Items", f"Status.{status.capitalize()}"), headers)

    async def get_item(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.items.READ")
        if err:
            return err
        item = state.data.items.get(request.path_params["item_id"])
        if item is None:
            return _zoho_error(404, 1002, "Item does not exist.", headers)
        return ok({"code": 0, "message": "success", "item": item}, headers)

    async def list_salesorders(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.salesorders.READ")
        if err:
            return err
        q = request.query_params
        status = _status_filter(q, "Status.All")
        records = [
            {k: v for k, v in so.items() if k not in {"line_items", "shipping_address", "billing_address"}}
            for so in state.data.salesorders.values()
            if (status == "all" or so["status"] == status)
            and _matches(
                q.get("search_text"), so["salesorder_number"], so["reference_number"], so["customer_name"]
            )
            and (
                not q.get("salesorder_number")
                or so["salesorder_number"].lower() == q["salesorder_number"].lower()
            )
            and (not q.get("customer_id") or so["customer_id"] == q["customer_id"])
            and (not q.get("date_start") or so["date"] >= q["date_start"])
            and (not q.get("date_end") or so["date"] <= q["date_end"])
        ]
        records.sort(
            key=lambda r: (r["date"], r["salesorder_number"]), reverse=q.get("sort_order", "D") == "D"
        )
        return ok(
            _paginate(records, request, "salesorders", "Sales Orders", f"Status.{status.capitalize()}"),
            headers,
        )

    async def get_salesorder(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.salesorders.READ")
        if err:
            return err
        so = state.data.salesorders.get(request.path_params["salesorder_id"])
        if so is None:
            return _zoho_error(404, 1002, "Sales order does not exist.", headers)
        return ok({"code": 0, "message": "success", "salesorder": so}, headers)

    async def list_contacts(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.contacts.READ")
        if err:
            return err
        q = request.query_params
        status = _status_filter(q, "Status.All")
        records = [
            {k: v for k, v in c.items() if k not in {"billing_address", "shipping_address"}}
            for c in state.data.contacts.values()
            if (status == "all" or c["status"] == status)
            and (not q.get("contact_type") or c["contact_type"] == q["contact_type"])
            and _matches(q.get("search_text"), c["contact_name"], c["company_name"], c["email"], c["phone"])
        ]
        records.sort(key=lambda r: r["contact_name"])
        return ok(
            _paginate(records, request, "contacts", "Contacts", f"Status.{status.capitalize()}"), headers
        )

    async def get_contact(request: Request) -> Response:
        err, headers = guard(request, "ZohoInventory.contacts.READ")
        if err:
            return err
        contact = state.data.contacts.get(request.path_params["contact_id"])
        if contact is None:
            return _zoho_error(404, 1002, "Contact does not exist.", headers)
        return ok({"code": 0, "message": "success", "contact": contact}, headers)

    async def health(_: Request) -> Response:
        return JSONResponse({"status": "ok", "api_calls": state.api_calls, "throttled": state.throttled})

    async def fail_next(request: Request) -> Response:
        statuses = [int(s) for s in request.query_params.get("statuses", "").split(",") if s]
        state.fail_next(*statuses)
        return JSONResponse({"queued": list(state.forced_failures)})

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/_mock/fail-next", fail_next, methods=["POST"]),
            Route("/oauth/v2/auth", authorize),
            Route("/oauth/v2/auth/approve", approve),
            Route("/oauth/v2/token", token, methods=["POST"]),
            Route("/oauth/v2/token/revoke", revoke, methods=["POST"]),
            Route("/inventory/v1/organizations", organizations),
            Route("/inventory/v1/items", list_items),
            Route("/inventory/v1/items/{item_id}", get_item),
            Route("/inventory/v1/salesorders", list_salesorders),
            Route("/inventory/v1/salesorders/{salesorder_id}", get_salesorder),
            Route("/inventory/v1/contacts", list_contacts),
            Route("/inventory/v1/contacts/{contact_id}", get_contact),
        ]
    )
    app.state.mock = state
    return app
