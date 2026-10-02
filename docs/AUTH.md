# Authentication

Zoho uses OAuth 2.0. The connector supports two setups:

| Setup | When to use | How it works |
|---|---|---|
| **Browser login** (`auth login`) | A merchant or operator on a laptop | Authorization-code flow with a localhost redirect and CSRF `state` check |
| **Self Client** (`auth exchange` or `ZOHO_REFRESH_TOKEN`) | Servers, containers, CI | A grant code is generated once in the Zoho console and exchanged for a long-lived refresh token |

Either way, the connector stores a **refresh token** and mints one-hour **access tokens** on demand.

## 1. Register a client

1. Open the Zoho API Console for your data centre, for example [api-console.zoho.in](https://api-console.zoho.in) (India) or [api-console.zoho.com](https://api-console.zoho.com) (US).
2. Choose **Server-based Applications**:
   - Homepage URL: anything (e.g. `http://localhost`)
   - Authorized Redirect URI: `http://localhost:8765/callback`
3. Copy the **Client ID** and **Client Secret** into `.env`:

```bash
ZOHO_CLIENT_ID=1000.XXXXXXXX
ZOHO_CLIENT_SECRET=xxxxxxxx
ZOHO_DATA_CENTER=in        # com | in | eu | com.au | jp | ca | sa | com.cn
```

## 2a. Browser login

```bash
zoho-inventory-mcp auth login        # opens the browser; use --no-browser on a remote shell
zoho-inventory-mcp orgs              # lists organization IDs
echo "ZOHO_ORGANIZATION_ID=600..." >> .env
zoho-inventory-mcp auth status       # confirms connection, scopes, token expiry, quota
```

What happens:

1. A random `state` value is generated, and a one-shot HTTP server listens on the redirect port.
2. The browser opens `https://accounts.zoho.<dc>/oauth/v2/auth` with `access_type=offline`, `prompt=consent` (so Zoho always issues a refresh token) and the read-only scopes.
3. Zoho redirects back with `code`, `state` and `accounts-server`. The state is compared in constant time; a mismatch aborts the login.
4. The code is exchanged at the **`accounts-server` returned by Zoho**. That matters for multi-DC accounts, where the user's account lives in a different region from the console they used.
5. Tokens are written atomically to `~/.config/zoho-inventory-mcp/tokens.json` with mode `0600`.

## 2b. Self Client (headless)

1. In the API Console, create a **Self Client**. Under **Generate Code**, enter the scopes below and a 10-minute expiry.
2. Exchange the code within its lifetime:

```bash
zoho-inventory-mcp auth exchange --code 1000.xxxx --accounts-server https://accounts.zoho.in
```

Alternatively, put an existing refresh token in `ZOHO_REFRESH_TOKEN`. The connector uses it to bootstrap and saves refreshed access tokens to the token store.

## Scopes

Read-only and least-privilege by default:

```
ZohoInventory.items.READ
ZohoInventory.salesorders.READ
ZohoInventory.contacts.READ
ZohoInventory.settings.READ     # needed for GET /organizations
```

## Token lifecycle

| Event | Behaviour |
|---|---|
| Access token within 60s of expiry | Refreshed before the request is sent |
| Many tool calls arrive while the token is expired | **Single-flight** refresh: one token request, all callers wait on it |
| Zoho returns 401 (token revoked or rotated early) | The token is invalidated, refreshed once and the request retried. A second 401 becomes a `PermissionDenied` error |
| Refresh token revoked | `AuthenticationRequired`, with a hint telling the agent not to retry and to ask the operator to log in again |
| `auth logout` | Calls Zoho's `/oauth/v2/token/revoke`, then deletes the local token file |

Zoho reports OAuth failures as HTTP 200 with an `{"error": "..."}` body. The connector checks the body, not just the status code.

## Security notes

- The client secret and tokens are loaded as `SecretStr` and are never included in tool output or logs.
- Run the MCP server with `--transport stdio` (the default) for local agents. The `streamable-http` transport has **no authentication of its own** in v1; only expose it on a private network or behind an authenticating gateway.
- To disconnect the connector, run `auth logout`, or remove the client under **Connected Apps** in Zoho Accounts.
