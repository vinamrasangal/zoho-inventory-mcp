from __future__ import annotations

import re
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from .client import ZohoInventoryClient
from .errors import InvalidRequest, NotFound, ZohoError
from .models import (
    ConnectionStatus,
    CustomerDetail,
    CustomerPage,
    CustomerSummary,
    ItemDetail,
    ItemPage,
    ItemSummary,
    LowStockReport,
    Page,
    SalesOrderDetail,
    SalesOrderPage,
    SalesOrderSummary,
)

ItemStatus = Literal["active", "inactive", "all"]
SalesOrderStatus = Literal["all", "draft", "confirmed", "closed", "void", "onhold"]
ItemSort = Literal["name", "sku", "rate", "stock_on_hand"]

M = TypeVar("M", bound=BaseModel)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    user, domain = email.split("@", 1)
    return f"{user[:1]}***@{domain}"


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    return f"******{digits[-4:]}" if len(digits) >= 4 else "******"


class InventoryService:
    """Read-only operations exposed to agents. Translates agent-friendly arguments into Zoho queries."""

    def __init__(self, client: ZohoInventoryClient) -> None:
        self.client = client
        self.settings = client.settings

    def _page_size(self, per_page: int | None) -> int:
        size = per_page or self.settings.default_page_size
        if not 1 <= size <= self.settings.max_page_size:
            raise InvalidRequest(f"per_page must be between 1 and {self.settings.max_page_size}.")
        return size

    @staticmethod
    def _check_page(page: int) -> None:
        if page < 1:
            raise InvalidRequest("page must be 1 or greater.")

    def _page(
        self,
        body: dict[str, Any],
        key: str,
        model: type[M],
        page: int,
        per_page: int,
        page_cls: type[Page[M]],
    ) -> Page[M]:
        has_more = bool(body.get("page_context", {}).get("has_more_page"))
        return page_cls(
            results=[self._redact(model.from_zoho(r)) for r in body.get(key, [])],  # type: ignore[attr-defined]
            page=page,
            per_page=per_page,
            has_more=has_more,
            next_page=page + 1 if has_more else None,
        )

    def _redact(self, model: M) -> M:
        if not self.settings.redact_pii:
            return model
        updates: dict[str, Any] = {}
        if isinstance(model, CustomerSummary):
            updates = {"email": _mask_email(model.email), "phone": _mask_phone(model.phone)}
            if isinstance(model, CustomerDetail):
                updates |= {
                    "billing_address": "[redacted]" if model.billing_address else None,
                    "shipping_address": "[redacted]" if model.shipping_address else None,
                }
        elif isinstance(model, SalesOrderDetail) and model.shipping_address:
            updates = {"shipping_address": "[redacted]"}
        return model.model_copy(update=updates) if updates else model

    # Items

    async def list_items(
        self,
        status: ItemStatus = "active",
        sort_by: ItemSort = "name",
        page: int = 1,
        per_page: int | None = None,
        query: str | None = None,
    ) -> ItemPage:
        self._check_page(page)
        size = self._page_size(per_page)
        body = await self.client.get(
            "/items",
            {
                "filter_by": f"Status.{status.capitalize()}",
                "sort_column": sort_by,
                "search_text": query,
                "page": page,
                "per_page": size,
            },
        )
        return self._page(body, "items", ItemSummary, page, size, ItemPage)

    async def get_item(self, item_id: str | None = None, sku: str | None = None) -> ItemDetail:
        if bool(item_id) == bool(sku):
            raise InvalidRequest("Provide exactly one of item_id or sku.")
        if sku:
            matches = (await self.client.get("/items", {"sku": sku, "filter_by": "Status.All"})).get(
                "items", []
            )
            exact = [m for m in matches if (m.get("sku") or "").lower() == sku.lower()]
            if not exact:
                raise NotFound(f"No item with SKU '{sku}'.")
            item_id = str(exact[0]["item_id"])
        body = await self.client.get(f"/items/{item_id}")
        return ItemDetail.from_zoho(body["item"])

    async def get_low_stock_items(self, limit: int = 50) -> LowStockReport:
        if not 1 <= limit <= 200:
            raise InvalidRequest("limit must be between 1 and 200.")
        records, truncated = await self.client.fetch_all(
            "/items",
            "items",
            {"filter_by": "Status.Active"},
            per_page=200,
            max_pages=self.settings.low_stock_scan_max_pages,
        )
        low = [i for i in map(ItemSummary.from_zoho, records) if i.is_low_stock]
        low.sort(key=lambda i: (i.available_stock or 0) - (i.reorder_level or 0))
        return LowStockReport(items=low[:limit], scanned_items=len(records), truncated=truncated)

    # Sales orders

    async def list_sales_orders(
        self,
        status: SalesOrderStatus = "all",
        customer_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        query: str | None = None,
        page: int = 1,
        per_page: int | None = None,
    ) -> SalesOrderPage:
        self._check_page(page)
        size = self._page_size(per_page)
        for label, value in (("date_from", date_from), ("date_to", date_to)):
            if value and not _DATE.match(value):
                raise InvalidRequest(f"{label} must be YYYY-MM-DD, got '{value}'.")
        body = await self.client.get(
            "/salesorders",
            {
                "filter_by": f"Status.{status.capitalize()}",
                "customer_id": customer_id,
                "date_start": date_from,
                "date_end": date_to,
                "search_text": query,
                "sort_column": "date",
                "sort_order": "D",
                "page": page,
                "per_page": size,
            },
        )
        result = self._page(body, "salesorders", SalesOrderSummary, page, size, SalesOrderPage)
        # Defensive client-side filter in case the date params are ignored upstream.
        if date_from or date_to:
            result.results = [
                so
                for so in result.results
                if so.date and (not date_from or so.date >= date_from) and (not date_to or so.date <= date_to)
            ]
        return result

    async def get_sales_order(
        self, salesorder_id: str | None = None, salesorder_number: str | None = None
    ) -> SalesOrderDetail:
        if bool(salesorder_id) == bool(salesorder_number):
            raise InvalidRequest("Provide exactly one of salesorder_id or salesorder_number.")
        if salesorder_number:
            body = await self.client.get(
                "/salesorders",
                {
                    "salesorder_number": salesorder_number,
                    "filter_by": "Status.All",
                },
            )
            exact = [
                s
                for s in body.get("salesorders", [])
                if (s.get("salesorder_number") or "").lower() == salesorder_number.lower()
            ]
            if not exact:
                raise NotFound(f"No sales order numbered '{salesorder_number}'.")
            salesorder_id = str(exact[0]["salesorder_id"])
        body = await self.client.get(f"/salesorders/{salesorder_id}")
        return self._redact(SalesOrderDetail.from_zoho(body["salesorder"]))

    # Customers

    async def list_customers(
        self, query: str | None = None, page: int = 1, per_page: int | None = None
    ) -> CustomerPage:
        self._check_page(page)
        size = self._page_size(per_page)
        body = await self.client.get(
            "/contacts",
            {
                "contact_type": "customer",
                "filter_by": "Status.Active",
                "search_text": query,
                "page": page,
                "per_page": size,
            },
        )
        return self._page(body, "contacts", CustomerSummary, page, size, CustomerPage)

    async def get_customer(self, customer_id: str) -> CustomerDetail:
        body = await self.client.get(f"/contacts/{customer_id}")
        return self._redact(CustomerDetail.from_zoho(body["contact"]))

    # Diagnostics

    async def connection_status(self) -> ConnectionStatus:
        limits = self.client.limiter.snapshot()
        try:
            tokens = await self.client.oauth.get_tokens()
            orgs = (await self.client.get("/organizations", org_scoped=False)).get("organizations", [])
        except ZohoError as exc:
            return ConnectionStatus(connected=False, rate_limits=limits, message=exc.for_agent())
        org_id = self.settings.organization_id
        org = next((o for o in orgs if str(o.get("organization_id")) == org_id), None)
        message = None
        if org is None:
            available = ", ".join(f"{o.get('name')} ({o.get('organization_id')})" for o in orgs)
            message = f"ZOHO_ORGANIZATION_ID '{org_id}' is not accessible. Available: {available or 'none'}."
        return ConnectionStatus(
            connected=org is not None,
            organization_id=org_id,
            organization_name=org.get("name") if org else None,
            api_domain=self.settings.resolved_api_url(tokens.api_domain),
            access_token_expires_in_seconds=max(0, int(tokens.expires_at - self.client.clock.time())),
            granted_scopes=tokens.scope,
            rate_limits=self.client.limiter.snapshot(),
            message=message,
        )
