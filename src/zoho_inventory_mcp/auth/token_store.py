from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class TokenSet(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: float
    api_domain: str | None = None
    accounts_server: str | None = None
    scope: str | None = None

    def is_expired(self, now: float, skew_seconds: float = 60.0) -> bool:
        return now >= self.expires_at - skew_seconds


class TokenStore(Protocol):
    def load(self) -> TokenSet | None: ...
    def save(self, tokens: TokenSet) -> None: ...
    def clear(self) -> None: ...


class FileTokenStore:
    """Stores tokens as JSON readable only by the current user (0600), written atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TokenSet | None:
        if not self.path.exists():
            return None
        return TokenSet.model_validate_json(self.path.read_text())

    def save(self, tokens: TokenSet) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tokens-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(tokens.model_dump(), f, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class MemoryTokenStore:
    def __init__(self, tokens: TokenSet | None = None) -> None:
        self.tokens = tokens

    def load(self) -> TokenSet | None:
        return self.tokens

    def save(self, tokens: TokenSet) -> None:
        self.tokens = tokens

    def clear(self) -> None:
        self.tokens = None
