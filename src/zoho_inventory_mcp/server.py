from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Annotated, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from . import __version__
from .errors import ZohoError
from .models import (
    ConnectionStatus,
    CustomerDetail,
    CustomerPage,
    ItemDetail,
    ItemPage,
    LowStockReport,
    SalesOrderDetail,
    SalesOrderPage,
)
from .service import InventoryService, ItemSort, ItemStatus, SalesOrderStatus

T = TypeVar("T")
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

INSTRUCTIONS = """\
Read-only access to one merchant's Zoho Inventory organization: items and stock levels,
sales orders, and customers. Nothing here can create, change or delete data.

How to use these tools well:
- Prefer search_* tools over paging through list_* results. Each call costs the merchant API quota.
- To look up an order or item the user names, search first, then call get_* with the returned ID
  (or pass the SKU / order number directly to get_item / get_sales_order).
- Stock: available_stock already subtracts quantities committed to open orders; use it to answer
  "can we fulfil this?". stock_on_hand is the physical count.
- Amounts are in the organization's currency (see currency_code). Dates are YYYY-MM-DD.
- If a tool returns an error, read its "Next step" hint. Do not retry auth or quota errors.
"""

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True
)

Page = Annotated[int, Field(ge=1, description="1-based page number.")]
PerPage = Annotated[int | None, Field(ge=1, le=200, description="Results per page (default 25, max 100).")]


async def _call(coro: Awaitable[T]) -> T:
    try:
        return await coro
    except ZohoError as exc:
        raise ToolError(exc.for_agent()) from exc


def create_server(service: InventoryService, log_level: LogLevel = "INFO") -> MCPServer:
    mcp = MCPServer(
        name="zoho-inventory",
        title="Zoho Inventory (read-only)",
        version=__version__,
        instructions=INSTRUCTIONS,
        log_level=log_level,
    )
    # httpx logs full request URLs at INFO; keep them out of the MCP server's stderr.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @mcp.tool(title="Connection status", annotations=READ_ONLY)
    async def connection_status() -> ConnectionStatus:
        """Check that Zoho Inventory is connected and show the organization, token expiry and remaining
        rate-limit budget. Call this first if other tools fail with auth or configuration errors."""
        return await service.connection_status()

    @mcp.tool(title="List items", annotations=READ_ONLY)
    async def list_items(
        status: Annotated[ItemStatus, Field(description="Filter by item status.")] = "active",
        sort_by: Annotated[ItemSort, Field(description="Sort column.")] = "name",
        page: Page = 1,
        per_page: PerPage = None,
    ) -> ItemPage:
        """Browse the product catalogue page by page with price and stock levels.
        Use search_items instead when looking for something specific."""
        return await _call(service.list_items(status, sort_by, page, per_page))

    @mcp.tool(title="Search items", annotations=READ_ONLY)
    async def search_items(
        query: Annotated[
            str,
            Field(
                min_length=1,
                description="Text matched against item name, SKU and description, e.g. 'masala chai'.",
            ),
        ],
        status: Annotated[ItemStatus, Field(description="Filter by item status.")] = "active",
        page: Page = 1,
        per_page: PerPage = None,
    ) -> ItemPage:
        """Find items by name, SKU or description. Returns price, stock on hand, available stock and
        a low-stock flag for each match."""
        return await _call(service.list_items(status, "name", page, per_page, query=query))

    @mcp.tool(title="Get item", annotations=READ_ONLY)
    async def get_item(
        item_id: Annotated[str | None, Field(description="Zoho item_id from a list/search result.")] = None,
        sku: Annotated[str | None, Field(description="Exact SKU, e.g. 'TEA-ASM-250'.")] = None,
    ) -> ItemDetail:
        """Get one item's full details including per-warehouse stock. Pass exactly one of item_id or sku."""
        return await _call(service.get_item(item_id, sku))

    @mcp.tool(title="Low-stock items", annotations=READ_ONLY)
    async def get_low_stock_items(
        limit: Annotated[int, Field(ge=1, le=200, description="Maximum items to return.")] = 50,
    ) -> LowStockReport:
        """List active items whose available stock is at or below their reorder level, most urgent first.
        Use this for 'what do I need to reorder?' questions. Scans the catalogue, so call it once and reuse
        the result rather than calling it repeatedly."""
        return await _call(service.get_low_stock_items(limit))

    @mcp.tool(title="List sales orders", annotations=READ_ONLY)
    async def list_sales_orders(
        status: Annotated[SalesOrderStatus, Field(description="Filter by order status.")] = "all",
        customer_id: Annotated[
            str | None, Field(description="Only this customer's orders (customer_id from search_customers).")
        ] = None,
        date_from: Annotated[str | None, Field(description="Order date on/after, YYYY-MM-DD.")] = None,
        date_to: Annotated[str | None, Field(description="Order date on/before, YYYY-MM-DD.")] = None,
        page: Page = 1,
        per_page: PerPage = None,
    ) -> SalesOrderPage:
        """List sales orders, newest first, optionally filtered by status, customer and date range."""
        return await _call(
            service.list_sales_orders(status, customer_id, date_from, date_to, page=page, per_page=per_page)
        )

    @mcp.tool(title="Search sales orders", annotations=READ_ONLY)
    async def search_sales_orders(
        query: Annotated[
            str,
            Field(
                min_length=1, description="Order number, reference number or customer name, e.g. 'SO-00042'."
            ),
        ],
        status: Annotated[SalesOrderStatus, Field(description="Filter by order status.")] = "all",
        page: Page = 1,
        per_page: PerPage = None,
    ) -> SalesOrderPage:
        """Find sales orders by order number, reference number or customer name."""
        return await _call(service.list_sales_orders(status, query=query, page=page, per_page=per_page))

    @mcp.tool(title="Get sales order", annotations=READ_ONLY)
    async def get_sales_order(
        salesorder_id: Annotated[str | None, Field(description="Zoho salesorder_id.")] = None,
        salesorder_number: Annotated[str | None, Field(description="Order number, e.g. 'SO-00042'.")] = None,
    ) -> SalesOrderDetail:
        """Get one sales order with line items, totals, and invoicing/payment/shipping status.
        Pass exactly one of salesorder_id or salesorder_number."""
        return await _call(service.get_sales_order(salesorder_id, salesorder_number))

    @mcp.tool(title="List customers", annotations=READ_ONLY)
    async def list_customers(page: Page = 1, per_page: PerPage = None) -> CustomerPage:
        """Browse active customers page by page. Use search_customers to find a specific one."""
        return await _call(service.list_customers(page=page, per_page=per_page))

    @mcp.tool(title="Search customers", annotations=READ_ONLY)
    async def search_customers(
        query: Annotated[str, Field(min_length=1, description="Name, company, email or phone fragment.")],
        page: Page = 1,
        per_page: PerPage = None,
    ) -> CustomerPage:
        """Find customers by name, company, email or phone. Returns customer_id for use with
        get_customer and list_sales_orders."""
        return await _call(service.list_customers(query, page, per_page))

    @mcp.tool(title="Get customer", annotations=READ_ONLY)
    async def get_customer(
        customer_id: Annotated[str, Field(min_length=1, description="customer_id from search_customers.")],
    ) -> CustomerDetail:
        """Get a customer's contact details, addresses, GSTIN and outstanding receivable."""
        return await _call(service.get_customer(customer_id))

    return mcp
