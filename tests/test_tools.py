"""Exercise the tools through the real MCP protocol with an in-process client."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from mcp import Client

from zoho_inventory_mcp.server import create_server

EXPECTED_TOOLS = {
    "connection_status",
    "list_items",
    "search_items",
    "get_item",
    "get_low_stock_items",
    "list_sales_orders",
    "search_sales_orders",
    "get_sales_order",
    "list_customers",
    "search_customers",
    "get_customer",
}


@pytest.fixture
def connect(make_harness) -> Callable[..., Any]:
    def factory(**settings: Any) -> Client:
        return Client(create_server(make_harness(**settings).service, log_level="ERROR"))

    return factory


async def call(client: Client, tool: str, **arguments: Any) -> dict[str, Any]:
    result = await client.call_tool(tool, arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def call_error(client: Client, tool: str, **arguments: Any) -> str:
    result = await client.call_tool(tool, arguments)
    assert result.is_error
    return result.content[0].text


async def test_tool_catalogue_is_read_only_and_documented(connect):
    async with connect() as client:
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.destructive_hint is False
            assert tool.description and len(tool.description) > 40
            assert tool.output_schema is not None


async def test_connection_status(connect):
    async with connect() as client:
        status = await call(client, "connection_status")
    assert status["connected"] is True
    assert status["organization_name"] == "Kesariya Foods Pvt Ltd"
    assert status["rate_limits"]["zoho_daily_remaining"] is not None


async def test_connection_status_reports_wrong_org(connect):
    async with connect(organization_id="999") as client:
        status = await call(client, "connection_status")
    assert status["connected"] is False
    assert "60012345678" in status["message"]


async def test_search_items(connect):
    async with connect() as client:
        page = await call(client, "search_items", query="saffron")
    skus = {r["sku"] for r in page["results"]}
    assert {"SPC-SAF-1G", "SPC-SAF-5G"} <= skus
    assert "GFT-DIW-01" in skus  # matched on description


async def test_list_items_pagination(connect):
    async with connect() as client:
        first = await call(client, "list_items", per_page=10)
        assert first["has_more"] and first["next_page"] == 2
        last = await call(client, "list_items", per_page=10, page=4)
        assert not last["has_more"] and last["next_page"] is None
        assert len(last["results"]) == 6  # 36 active items
        assert {r["item_id"] for r in first["results"]}.isdisjoint(r["item_id"] for r in last["results"])


async def test_inactive_items_are_excluded_by_default(connect):
    async with connect() as client:
        active = await call(client, "search_items", query="old pack")
        everything = await call(client, "search_items", query="old pack", status="all")
        assert active["results"] == []
        assert everything["results"][0]["status"] == "inactive"


async def test_get_item_by_sku_includes_warehouse_breakdown(connect):
    async with connect() as client:
        item = await call(client, "get_item", sku="tea-msl-250")
    assert item["sku"] == "TEA-MSL-250"
    assert len(item["warehouses"]) == 2
    assert sum(w["stock_on_hand"] for w in item["warehouses"]) == item["stock_on_hand"]


async def test_get_item_requires_exactly_one_identifier(connect):
    async with connect() as client:
        assert "exactly one" in await call_error(client, "get_item")
        assert "exactly one" in await call_error(client, "get_item", item_id="1", sku="X")


async def test_not_found_errors_tell_the_agent_what_to_do(connect):
    async with connect() as client:
        text = await call_error(client, "get_item", item_id="does-not-exist")
    assert "does not exist" in text and "search tool" in text


async def test_low_stock_items_are_sorted_by_urgency(connect):
    async with connect() as client:
        report = await call(client, "get_low_stock_items")
    items = report["items"]
    assert items and all(i["is_low_stock"] for i in items)
    shortfalls = [i["available_stock"] - i["reorder_level"] for i in items]
    assert shortfalls == sorted(shortfalls)
    assert report["scanned_items"] == 36 and report["truncated"] is False


async def test_list_sales_orders_filters(connect):
    async with connect() as client:
        page = await call(
            client,
            "list_sales_orders",
            status="confirmed",
            date_from="2026-09-01",
            date_to="2026-09-30",
            per_page=100,
        )
        assert page["results"]
        assert all(
            r["status"] == "confirmed" and "2026-09-01" <= r["date"] <= "2026-09-30" for r in page["results"]
        )
        dates = [r["date"] for r in page["results"]]
        assert dates == sorted(dates, reverse=True)


async def test_rejects_malformed_dates(connect):
    async with connect() as client:
        assert "YYYY-MM-DD" in await call_error(client, "list_sales_orders", date_from="01/09/2026")


async def test_customer_to_orders_workflow(connect):
    async with connect() as client:
        customers = await call(client, "search_customers", query="Chaayos")
        customer = customers["results"][0]
        orders = await call(client, "list_sales_orders", customer_id=customer["customer_id"], per_page=100)
        assert all(o["customer_id"] == customer["customer_id"] for o in orders["results"])
        detail = await call(client, "get_customer", customer_id=customer["customer_id"])
        assert detail["gst_no"]


async def test_vendors_are_not_returned_as_customers(connect):
    async with connect() as client:
        page = await call(client, "search_customers", query="Leaf")
    assert page["results"] == []


async def test_get_sales_order_by_number(connect):
    async with connect() as client:
        order = await call(client, "get_sales_order", salesorder_number="SO-00042")
        assert order["line_items"]
        assert order["total"] == pytest.approx(
            order["sub_total"] + order["tax_total"] + order["shipping_charge"]
        )
        found = await call(client, "search_sales_orders", query="SO-00042")
        assert found["results"][0]["salesorder_id"] == order["salesorder_id"]


async def test_page_size_is_capped(connect):
    async with connect() as client:
        assert "per_page" in await call_error(client, "list_items", per_page=150)


async def test_pii_redaction(connect):
    async with connect(redact_pii=True) as client:
        customer = (await call(client, "search_customers", query="Chaayos"))["results"][0]
        assert customer["email"].startswith("p***@")
        assert customer["phone"].startswith("******")
        order = await call(client, "get_sales_order", salesorder_number="SO-00042")
        assert order["shipping_address"] == "[redacted]"
