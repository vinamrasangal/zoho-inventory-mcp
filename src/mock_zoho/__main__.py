from __future__ import annotations

import argparse

import uvicorn

from .app import MockConfig, create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock Zoho accounts + Inventory API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8800)
    parser.add_argument("--rate-limit-per-minute", type=int, default=100)
    parser.add_argument("--token-ttl", type=int, default=3600, help="Access-token lifetime in seconds.")
    args = parser.parse_args()

    config = MockConfig(
        base_url=f"http://{args.host}:{args.port}",
        rate_limit_per_minute=args.rate_limit_per_minute,
        token_ttl_seconds=args.token_ttl,
    )
    print(
        f"Mock Zoho running at {config.base_url}  (client_id={config.client_id}, "
        f"client_secret={config.client_secret}, self-client refresh token={config.self_client_refresh_token})"
    )
    uvicorn.run(create_app(config), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
