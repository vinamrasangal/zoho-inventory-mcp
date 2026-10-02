"""End-to-end demo: mock Zoho + the MCP server over stdio + a scripted merchant conversation.

Run with `make demo` (or `python scripts/demo.py`). No Zoho account or API keys needed.
The MCP server runs as a real subprocess and every call goes through the MCP protocol,
exactly as it would from Agent Studio, Claude Desktop or Cursor.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from mock_zoho import MockConfig, create_app
from mock_zoho.data import ORG_ID

BOLD, DIM, CYAN, GREEN, RED, RESET = "\033[1m", "\033[2m", "\033[36m", "\033[32m", "\033[31m", "\033[0m"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_mock(port: int) -> None:
    app = create_app(MockConfig(base_url=f"http://127.0.0.1:{port}"))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.2)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("mock server did not start")


def ask(question: str) -> None:
    print(f"\n{BOLD}Merchant:{RESET} {question}")


async def tool(client: Client, name: str, **arguments: Any) -> dict[str, Any] | None:
    print(f"  {CYAN}→ {name}({json.dumps(arguments) if arguments else ''}){RESET}")
    started = time.perf_counter()
    result = await client.call_tool(name, arguments)
    elapsed = (time.perf_counter() - started) * 1000
    if result.is_error:
        print(f"  {RED}✗ error ({elapsed:.0f} ms):{RESET} {result.content[0].text}")
        return None
    print(f"  {DIM}✓ {elapsed:.0f} ms{RESET}")
    return result.structured_content


def say(text: str) -> None:
    print(f"  {GREEN}Agent:{RESET} {text}")


async def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    port = free_port()
    start_mock(port)
    base = f"http://127.0.0.1:{port}"
    token_dir = tempfile.mkdtemp(prefix="zoho-demo-")
    env = {
        **os.environ,
        "ZOHO_CLIENT_ID": "mock-client-id",
        "ZOHO_CLIENT_SECRET": "mock-client-secret",
        "ZOHO_ACCOUNTS_URL": base,
        "ZOHO_REFRESH_TOKEN": "mock-refresh-token",
        "ZOHO_ORGANIZATION_ID": ORG_ID,
        "ZOHO_TOKEN_STORE_PATH": str(Path(token_dir) / "tokens.json"),
        "ZOHO_BACKOFF_BASE_SECONDS": "0.2",
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "zoho_inventory_mcp", "serve"], env=env
    )

    print(f"{BOLD}Zoho Inventory MCP connector — demo{RESET}  {DIM}(mock Zoho at {base}){RESET}")
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        print(
            f"{DIM}MCP server exposes {len(tools)} read-only tools: {', '.join(t.name for t in tools)}{RESET}"
        )

        ask("Are we connected?")
        status = await tool(client, "connection_status")
        if status:
            say(
                f"Yes — connected to {status['organization_name']} ({status['organization_id']}). "
                f"{status['rate_limits']['zoho_daily_remaining']} API calls left today."
            )

        ask("What do I need to reorder this week?")
        report = await tool(client, "get_low_stock_items", limit=5)
        if report:
            say(
                f"{len(report['items'])} most urgent of the low-stock items (scanned {report['scanned_items']}):"
            )
            for item in report["items"]:
                print(
                    f"     • {item['name']:<32} available {item['available_stock']:>5.0f}"
                    f"   reorder at {item['reorder_level']:.0f}"
                )

        ask("Can we ship 10 packs of Kesar Saffron 5g from Mumbai?")
        item = await tool(client, "get_item", sku="SPC-SAF-5G")
        if item:
            mumbai = next(w for w in item["warehouses"] if "Mumbai" in w["warehouse_name"])
            verdict = "Yes" if mumbai["available_stock"] >= 10 else "No"
            say(
                f"{verdict} — Mumbai has {mumbai['available_stock']:.0f} available "
                f"({item['available_stock']:.0f} across all warehouses)."
            )

        ask("What has Chaayos ordered recently, and is anything still open?")
        customers = await tool(client, "search_customers", query="Chaayos")
        if customers and customers["results"]:
            customer = customers["results"][0]
            orders = await tool(client, "list_sales_orders", customer_id=customer["customer_id"], per_page=5)
            if orders:
                open_orders = [
                    o for o in orders["results"] if o["status"] in ("confirmed", "onhold", "draft")
                ]
                say(
                    f"{customer['name']} has {len(orders['results'])} recent orders; {len(open_orders)} still open. "
                    f"Outstanding receivable: ₹{customer['outstanding_receivable']:,.0f}."
                )
                for o in orders["results"]:
                    print(
                        f"     • {o['salesorder_number']}  {o['date']}  {o['status']:<9} ₹{o['total']:>9,.2f}"
                    )

        ask("What's in order SO-00087 and has it shipped?")
        order = await tool(client, "get_sales_order", salesorder_number="SO-00087")
        if order:
            lines = ", ".join(f"{li['quantity']:.0f}× {li['name']}" for li in order["line_items"])
            say(
                f"{order['salesorder_number']} for {order['customer_name']}: {lines}. "
                f"Status {order['status']}, shipping {order['shipped_status'] or 'n/a'}, total ₹{order['total']:,.2f}."
            )

        print(
            f"\n{BOLD}Resilience:{RESET} Zoho will now answer the next call with 429 Too Many Requests, then 503."
        )
        httpx.post(f"{base}/_mock/fail-next", params={"statuses": "429,503"})
        ask("Find our masala products.")
        found = await tool(client, "search_items", query="masala", per_page=3)
        if found:
            say(
                f"Found {len(found['results'])}+ items (connector retried transparently): "
                + ", ".join(r["name"] for r in found["results"])
            )

        print(f"\n{BOLD}Guardrails:{RESET} errors come back with a next step the agent can act on.")
        ask("Look up item 12345.")
        await tool(client, "get_item", item_id="12345")

    calls = httpx.get(f"{base}/health").json()
    print(f"\n{DIM}Done. {calls['api_calls']} Zoho API calls made.{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
