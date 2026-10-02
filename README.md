# Zoho Inventory MCP Connector

[![CI](https://github.com/vinamrasangal/zoho-inventory-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/vinamrasangal/zoho-inventory-mcp/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![MCP](https://img.shields.io/badge/MCP-2.x-8A2BE2)
![License](https://img.shields.io/badge/license-MIT-green)

A private, **read-only** connector that lets an AI agent answer a merchant's day-to-day questions from **Zoho Inventory**: stock levels, reorder alerts, sales orders and customers. It is exposed as an [MCP](https://modelcontextprotocol.io) server, so it plugs into Agent Studio, Claude, Cursor or any other MCP host.

> *"What do I need to reorder?"* · *"Can we ship 10 saffron packs from Mumbai?"* · *"What's still open for Chaayos?"* · *"Has SO-00087 shipped?"*

**What's included**

- **OAuth 2.0:** browser login with CSRF `state`, multi-data-centre support, refresh tokens, single-flight refresh, revoke on logout, and a `0600` token store. A headless Self Client flow is available for servers. See [docs/AUTH.md](docs/AUTH.md).
- **11 list / get / search tools** with typed input *and* output schemas, plus `readOnlyHint` annotations. Spec: [docs/tool-spec.json](docs/tool-spec.json).
- **Rate-limit handling that prevents 429s rather than just retrying them:** a sliding-window limiter, a concurrency cap, a daily budget that protects the merchant's shared quota, and Retry-After-aware backoff with jitter.
- **Errors designed for agents:** each failure tells the model what to do next, so it doesn't loop.
- **Runs without a Zoho account:** a high-fidelity mock Zoho (OAuth and Inventory API) powers the tests, the demo and local development.
- **45 tests and CI,** including a test that drives the server over stdio exactly as an agent host would.
- **A clear statement of what the agent can and cannot do:** [docs/CAPABILITIES.md](docs/CAPABILITIES.md).

---

## Try it in 2 minutes (no Zoho account needed)

```bash
git clone https://github.com/vinamrasangal/zoho-inventory-mcp.git
cd zoho-inventory-mcp
make install     # creates .venv and installs the package with dev tools
make demo        # mock Zoho + MCP server over stdio + scripted merchant conversation
```

<details>
<summary>Demo output</summary>

```text
Zoho Inventory MCP connector — demo  (mock Zoho at http://127.0.0.1:56653)
MCP server exposes 11 read-only tools: connection_status, list_items, search_items, get_item, ...

Merchant: What do I need to reorder this week?
  → get_low_stock_items({"limit": 5})
  ✓ 6 ms
  Agent: 5 most urgent of the low-stock items (scanned 36):
     • Assam Breakfast Tea 250g         available    16   reorder at 40
     • Chai Lovers Gift Box             available     8   reorder at 30
     • Jaggery Powder 500g              available     5   reorder at 25
     • A2 Ghee 500ml                    available     2   reorder at 15
     • Kesar Saffron 5g                 available     0   reorder at 10

Merchant: What has Chaayos ordered recently, and is anything still open?
  → search_customers({"query": "Chaayos"})
  → list_sales_orders({"customer_id": "230000000100001", "per_page": 5})
  Agent: Chaayos Retail LLP has 5 recent orders; 3 still open. Outstanding receivable: ₹15,400.

Resilience: Zoho will now answer the next call with 429 Too Many Requests, then 503.
Merchant: Find our masala products.
  → search_items({"query": "masala", "per_page": 3})
  ✓ 1195 ms
  Agent: Found 3+ items (connector retried transparently): Biryani Masala 100g, Garam Masala 100g, ...

Guardrails: errors come back with a next step the agent can act on.
Merchant: Look up item 12345.
  → get_item({"item_id": "12345"})
  ✗ error: Item does not exist. Next step: Check the identifier; use a search tool to find the right ID before retrying.
```
</details>

### Use it from an agent (Cursor / Claude Desktop) against the mock

```bash
make mock                                   # terminal 1: mock Zoho on :8800
```

Copy [`examples/mcp.mock.json`](examples/mcp.mock.json) into your MCP client config (Cursor: `~/.cursor/mcp.json`; Claude Desktop: `claude_desktop_config.json`), fix the absolute path, and ask *"Which products are below their reorder level?"*

### Call a tool from the shell

```bash
cp .env.example .env    # then uncomment the mock block at the bottom
zoho-inventory-mcp call search_items '{"query": "chai"}'
zoho-inventory-mcp call get_sales_order '{"salesorder_number": "SO-00042"}'
```

---

## Connect a real Zoho Inventory organization

```bash
cp .env.example .env                      # add ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_DATA_CENTER
zoho-inventory-mcp auth login             # browser consent → tokens saved (0600)
zoho-inventory-mcp orgs                   # pick your organization ID → ZOHO_ORGANIZATION_ID in .env
zoho-inventory-mcp auth status            # verify: org, scopes, token expiry, remaining quota
zoho-inventory-mcp serve                  # stdio MCP server (use examples/mcp.json in your host)
```

Step-by-step client registration, the Self Client (headless) flow and the token lifecycle are covered in [docs/AUTH.md](docs/AUTH.md).

---

## Tools

| Tool | Purpose | Key inputs |
|---|---|---|
| `connection_status` | Connected? Which org? Token expiry, remaining rate-limit and quota | – |
| `list_items` | Browse the catalogue with price and stock | `status`, `sort_by`, `page`, `per_page` |
| `search_items` | Find items by name, SKU or description | `query` |
| `get_item` | Full item detail with **per-warehouse** stock | `item_id` **or** `sku` |
| `get_low_stock_items` | Items at or below reorder level, most urgent first | `limit` |
| `list_sales_orders` | Newest-first orders filtered by status, customer, date range | `status`, `customer_id`, `date_from`, `date_to` |
| `search_sales_orders` | Find orders by number, reference or customer name | `query` |
| `get_sales_order` | Line items, totals, invoice / payment / shipping status | `salesorder_id` **or** `salesorder_number` |
| `list_customers` | Browse active customers | `page`, `per_page` |
| `search_customers` | Find customers by name, company, email or phone | `query` |
| `get_customer` | Contact details, addresses, GSTIN, outstanding receivable | `customer_id` |

The full MCP specification (descriptions, JSON Schemas for inputs and outputs, annotations, server instructions) is generated from code into [`docs/tool-spec.json`](docs/tool-spec.json). CI fails if it drifts from the code.

## Rate limiting in one paragraph

Zoho allows roughly 100 requests per minute per organization, a handful of concurrent calls, and a daily quota that is **shared with the merchant's other integrations**. The connector enforces all three on the client side: a sliding 60-second window, a concurrency semaphore, and an optional `ZOHO_DAILY_REQUEST_BUDGET`. It also reads Zoho's `X-Rate-Limit-Remaining` header. If a 429 still arrives, every in-flight call cools down together, honouring `Retry-After`. 5xx and network errors use exponential backoff with full jitter. The tests check that a correctly configured connector sends **zero** 429s, and that a misconfigured one recovers. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#rate-limiting-prevent-first-recover-second).

## Configuration

All settings are environment variables (or `.env`). The common ones:

| Variable | Default | Notes |
|---|---|---|
| `ZOHO_CLIENT_ID` / `ZOHO_CLIENT_SECRET` | – | From the Zoho API Console |
| `ZOHO_DATA_CENTER` | `com` | `in`, `eu`, `com.au`, `jp`, `ca`, `sa`, `com.cn` |
| `ZOHO_ORGANIZATION_ID` | – | Run `zoho-inventory-mcp orgs` to find it |
| `ZOHO_REFRESH_TOKEN` | – | Headless bootstrap (Self Client) |
| `ZOHO_RATE_LIMIT_PER_MINUTE` | `100` | Lower it if other integrations share the org |
| `ZOHO_MAX_CONCURRENCY` | `5` | Zoho's limit on the lowest plans |
| `ZOHO_DAILY_REQUEST_BUDGET` | unset | Hard cap on this connector's share of the daily quota |
| `ZOHO_MAX_RETRIES` | `4` | For 429 / 5xx / network errors |
| `ZOHO_REDACT_PII` | `false` | Mask customer email, phone and addresses |

The full list is in [`config.py`](src/zoho_inventory_mcp/config.py).

## Project layout

```
src/zoho_inventory_mcp/
  server.py        MCP tools: schemas, descriptions, annotations, error → isError
  service.py       agent-friendly operations → Zoho queries; PII redaction
  client.py        HTTP: auth header, org scoping, retries/backoff, 401 refresh, pagination
  rate_limit.py    sliding window + concurrency + daily budget + cooldown
  auth/            OAuth manager, localhost login flow, token store
  models.py        compact, typed response models
  cli.py           auth login|exchange|status|logout, orgs, serve, call, export-spec
src/mock_zoho/     Starlette mock of Zoho Accounts + Inventory API (OAuth, scopes, 429s, failure injection)
tests/             45 tests: OAuth, resilience, rate limiter, tools over MCP
scripts/demo.py    end-to-end demo over stdio (also run in CI)
docs/              CAPABILITIES, AUTH, ARCHITECTURE, tool-spec.json
```

## Development

```bash
make test        # pytest
make lint        # ruff check + format check
make spec        # regenerate docs/tool-spec.json
```

## Assumptions & limitations

- Built and tested against the mock because no live Zoho organization was available during development. The handful of API behaviours that should be confirmed on a real organization are listed in [CAPABILITIES.md → Assumptions](docs/CAPABILITIES.md#assumptions-to-verify-against-a-live-organization).
- Read-only by design. Invoices, shipments and purchase orders are out of scope for v1.
- Single tenant: one Zoho organization per server process. The `streamable-http` transport has no built-in auth, so keep it on a private network or use `stdio`.
- The roadmap (writes with human approval, multi-tenant token vault, webhooks) is in [CAPABILITIES.md → Roadmap](docs/CAPABILITIES.md#roadmap-if-this-went-to-production).

## License

MIT
