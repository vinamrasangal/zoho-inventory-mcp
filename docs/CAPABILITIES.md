# What the agent can and cannot do

This connector gives an agent **read-only** access to **one** Zoho Inventory organization. This page describes what that means in practice. It is written for a merchant deciding whether to connect their account, and for an engineer deciding what to build on top of it.

## The agent can

| Area | Questions it can answer | Tools |
|---|---|---|
| **Catalogue & pricing** | "What do we sell under ₹500?", "What's the SKU for the masala chai 500g?", "Show inactive products." | `list_items`, `search_items`, `get_item` |
| **Stock** | "How many Assam 250g packs can we ship today?", "How is saffron stock split between Bengaluru and Mumbai?" | `get_item` (per-warehouse), `search_items` |
| **Reordering** | "What do I need to reorder?", "Which items are already at zero?" | `get_low_stock_items` |
| **Orders** | "Where is SO-00042?", "What's still open for Chaayos?", "Orders placed in the last week?", "Has the corporate order shipped?" | `search_sales_orders`, `list_sales_orders`, `get_sales_order` |
| **Customers** | "Find the customer with phone ending 4821", "What's Hotel Sea Breeze's GSTIN and outstanding balance?" | `search_customers`, `list_customers`, `get_customer` |
| **Self-diagnosis** | "Why can't you see my data?" Shows connection state, organization, token expiry and remaining API quota. | `connection_status` |

All tools return typed, compact JSON with a published output schema (see [`tool-spec.json`](tool-spec.json)). Every tool is annotated `readOnlyHint: true, destructiveHint: false`, so an MCP host can safely skip per-call confirmation.

## The agent cannot

| Cannot | Why |
|---|---|
| **Create, edit, cancel or delete anything** (orders, items, stock adjustments, customers) | No write tools exist, and the OAuth scopes requested are `*.READ` only. Even a prompt-injected agent cannot change data, because Zoho will refuse it. |
| **See other Zoho organizations or apps** (Books, CRM, Desk) | Every request is pinned to `ZOHO_ORGANIZATION_ID`, and no other scopes are granted. |
| **See invoices, payments, bills, purchase orders, packages/shipments, or vendors** | Out of scope for v1 (vendors are filtered out of customer results). Order-level `invoiced_status`, `paid_status` and `shipped_status` are exposed instead. |
| **Read item images, attachments, custom fields or audit history** | These are not mapped into the response models, to keep payloads small. |
| **Run unbounded scans** | Page size is capped at 100. `get_low_stock_items` scans at most `ZOHO_LOW_STOCK_SCAN_MAX_PAGES` × 200 items and reports `truncated: true` if the catalogue is larger. |
| **Exceed the merchant's API quota** | A client-side limiter enforces the per-minute and concurrency limits, plus an optional daily budget, so the agent cannot starve the merchant's other integrations. |
| **Analytics across the full order history** (e.g. "best-selling SKU this year") | There is no aggregate endpoint. It would mean paging through every order, which is slow and quota-hungry. Use Zoho's reports, or a warehouse sync, for this. |
| **Real-time push** (e.g. "tell me when stock drops") | Pull-only. Webhooks are on the roadmap below. |

## Data handling

- **PII:** customer email, phone and addresses are returned by default because agents often need them, for example to draft a follow-up. Set `ZOHO_REDACT_PII=true` to mask email and phone (`p***@domain`, `******4821`) and replace addresses with `[redacted]`.
- **Credentials** never reach the agent. Tokens live in a `0600` file (or are injected through the environment), and httpx request logging is suppressed so URLs and headers don't reach logs.
- **Errors** are returned as `isError` tool results with a `Next step:` hint, for example "use a search tool to find the right ID" or "do not retry; ask the operator to run `auth login`". This stops the agent from looping on errors it cannot fix.

## Assumptions to verify against a live organization

The connector was built and tested against a high-fidelity mock (`src/mock_zoho`) because no live Zoho organization was available. The behaviors below follow Zoho's public docs but should be confirmed on a real organization before production:

1. `GET /salesorders` honours `date_start` / `date_end`. A defensive client-side date filter is applied in case it doesn't.
2. `GET /contacts?contact_type=customer` filters out vendors.
3. Sales-order `filter_by` values map to `Status.<Capitalised>` (e.g. `Status.Confirmed`). `onhold` may need to be `Status.OnHold`.
4. The `X-Rate-Limit-*` daily-quota headers are present. If they aren't, the connector relies on its own counter and `ZOHO_DAILY_REQUEST_BUDGET`.
5. A revoked or expired access token returns HTTP 401. The connector refreshes once on 401 and then surfaces a permission error.

## Roadmap (if this went to production)

- **Write tools behind human approval:** e.g. `draft_sales_order`, `adjust_stock`. These would use MCP elicitation for confirmation, separate write scopes, and idempotency keys.
- **Multi-tenant hosting:** one token vault per merchant (KMS-encrypted), Streamable HTTP with OAuth on the MCP side, and per-tenant rate-limit state in Redis.
- **Webhooks:** subscribe to Zoho Inventory webhooks for stock and order changes, and cache hot reads to cut quota usage.
- **More resources:** invoices, packages/shipments (tracking numbers), purchase orders (for "when is stock arriving?"), and composite items.
