from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DataCenter = Literal["com", "in", "eu", "com.au", "jp", "ca", "sa", "com.cn"]

# Least-privilege, read-only scopes. `settings.READ` is needed for /organizations.
DEFAULT_SCOPES = (
    "ZohoInventory.items.READ",
    "ZohoInventory.salesorders.READ",
    "ZohoInventory.contacts.READ",
    "ZohoInventory.settings.READ",
)


class Settings(BaseSettings):
    """Connector configuration, read from `ZOHO_*` environment variables or a `.env` file."""

    model_config = SettingsConfigDict(env_prefix="ZOHO_", env_file=".env", extra="ignore")

    client_id: str | None = None
    client_secret: SecretStr | None = None
    redirect_uri: str = "http://localhost:8765/callback"
    data_center: DataCenter = "com"
    accounts_url: str | None = Field(
        default=None, description="Override the accounts server (e.g. a mock). Derived from data_center."
    )
    api_url: str | None = Field(
        default=None, description="Override the API domain. Defaults to the api_domain returned by OAuth."
    )
    scopes: tuple[str, ...] = DEFAULT_SCOPES

    organization_id: str | None = None
    refresh_token: SecretStr | None = Field(
        default=None, description="Headless bootstrap: a refresh token from a Zoho Self Client."
    )
    token_store_path: Path = Path("~/.config/zoho-inventory-mcp/tokens.json")

    rate_limit_per_minute: int = Field(default=100, ge=1)
    max_concurrency: int = Field(default=5, ge=1)
    daily_request_budget: int | None = Field(default=None, ge=1)
    max_retries: int = Field(default=4, ge=0)
    backoff_base_seconds: float = Field(default=0.5, gt=0)
    backoff_max_seconds: float = Field(default=30.0, gt=0)
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    default_page_size: int = Field(default=25, ge=1, le=200)
    max_page_size: int = Field(default=100, ge=1, le=200)
    low_stock_scan_max_pages: int = Field(default=10, ge=1)
    redact_pii: bool = False

    @property
    def resolved_accounts_url(self) -> str:
        return (self.accounts_url or f"https://accounts.zoho.{self.data_center}").rstrip("/")

    def resolved_api_url(self, token_api_domain: str | None = None) -> str:
        url = self.api_url or token_api_domain or f"https://www.zohoapis.{self.data_center}"
        return url.rstrip("/")

    @property
    def token_path(self) -> Path:
        return self.token_store_path.expanduser()
