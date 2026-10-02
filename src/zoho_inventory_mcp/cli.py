from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .auth.login_flow import interactive_login
from .config import Settings
from .errors import ZohoError
from .factory import build_service
from .server import create_server


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


async def _auth_login(args: argparse.Namespace) -> None:
    service = build_service()
    tokens = await interactive_login(service.client.oauth, open_browser=not args.no_browser)
    print(f"Connected. Tokens saved to {service.settings.token_path} (API domain: {tokens.api_domain}).")
    print("Next: run `zoho-inventory-mcp orgs` and set ZOHO_ORGANIZATION_ID.")


async def _auth_exchange(args: argparse.Namespace) -> None:
    service = build_service()
    tokens = await service.client.oauth.exchange_code(args.code, accounts_server=args.accounts_server)
    print(f"Connected. Tokens saved to {service.settings.token_path} (API domain: {tokens.api_domain}).")


async def _auth_status(_: argparse.Namespace) -> None:
    _print_json((await build_service().connection_status()).model_dump())


async def _auth_logout(_: argparse.Namespace) -> None:
    revoked = await build_service().client.oauth.revoke()
    print("Refresh token revoked and local tokens deleted." if revoked else "Local tokens deleted.")


async def _orgs(_: argparse.Namespace) -> None:
    body = await build_service().client.get("/organizations", org_scoped=False)
    for org in body.get("organizations", []):
        print(f"{org.get('organization_id')}\t{org.get('name')}\t{org.get('currency_code', '')}")


async def _call(args: argparse.Namespace) -> None:
    from mcp import Client

    arguments = json.loads(args.arguments) if args.arguments else {}
    async with Client(create_server(build_service(), log_level="ERROR")) as client:
        result = await client.call_tool(args.tool, arguments)
    if result.is_error:
        print("\n".join(getattr(c, "text", "") for c in result.content), file=sys.stderr)
        raise SystemExit(1)
    _print_json(result.structured_content)


async def _export_spec(args: argparse.Namespace) -> None:
    server = create_server(build_service(Settings(_env_file=None)), log_level="ERROR")
    tools = [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in await server.list_tools()]
    spec = {"name": server.name, "version": __version__, "instructions": server.instructions, "tools": tools}
    text = json.dumps(spec, indent=2) + "\n"
    if args.out:
        await asyncio.to_thread(Path(args.out).write_text, text)
        print(f"Wrote {len(tools)} tool definitions to {args.out}")
    else:
        print(text)


def _serve(args: argparse.Namespace) -> None:
    server = create_server(build_service())
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zoho-inventory-mcp", description=__doc__ or "Read-only MCP connector for Zoho Inventory."
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Run the MCP server.")
    serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(handler=_serve, sync=True)

    auth = sub.add_parser("auth", help="Manage the Zoho OAuth connection.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="Connect via the browser consent flow.")
    login.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening it.")
    login.set_defaults(handler=_auth_login)
    exchange = auth_sub.add_parser("exchange", help="Exchange a Self Client grant code (headless setup).")
    exchange.add_argument("--code", required=True)
    exchange.add_argument("--accounts-server", help="e.g. https://accounts.zoho.in")
    exchange.set_defaults(handler=_auth_exchange)
    auth_sub.add_parser("status", help="Show connection, token and quota status.").set_defaults(
        handler=_auth_status
    )
    auth_sub.add_parser("logout", help="Revoke the refresh token and delete it locally.").set_defaults(
        handler=_auth_logout
    )

    sub.add_parser("orgs", help="List organizations the connected user can access.").set_defaults(
        handler=_orgs
    )

    call = sub.add_parser("call", help="Invoke one tool through the MCP protocol and print the result.")
    call.add_argument("tool")
    call.add_argument("arguments", nargs="?", help='JSON object, e.g. \'{"query": "chai"}\'')
    call.set_defaults(handler=_call)

    spec = sub.add_parser("export-spec", help="Write the MCP tool specification as JSON.")
    spec.add_argument("--out", help="Output path (default: stdout).")
    spec.set_defaults(handler=_export_spec)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        if getattr(args, "sync", False):
            args.handler(args)
        else:
            asyncio.run(args.handler(args))
    except ZohoError as exc:
        print(f"Error: {exc.for_agent()}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
