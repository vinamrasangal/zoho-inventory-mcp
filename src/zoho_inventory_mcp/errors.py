from __future__ import annotations


class ZohoError(Exception):
    """Base error. `hint` is written for the calling agent: what it should do next."""

    hint: str = "Report the error to the user."

    def __init__(
        self, message: str, *, hint: str | None = None, status: int | None = None, code: int | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        if hint is not None:
            self.hint = hint

    def for_agent(self) -> str:
        return f"{self.message} Next step: {self.hint}"


class ConfigurationError(ZohoError):
    hint = "The connector is misconfigured; ask the operator to check the ZOHO_* settings."


class AuthenticationRequired(ZohoError):
    hint = (
        "The merchant has not connected Zoho Inventory (or revoked access). "
        "Ask the operator to run `zoho-inventory-mcp auth login`. Do not retry."
    )


class PermissionDenied(ZohoError):
    hint = "The connected Zoho user or OAuth scopes do not allow this. Do not retry; tell the user."


class NotFound(ZohoError):
    hint = "Check the identifier; use a search tool to find the right ID before retrying."


class InvalidRequest(ZohoError):
    hint = "Fix the arguments (see the message) and retry once."


class RateLimited(ZohoError):
    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        wait = f"about {retry_after:.0f}s" if retry_after else "a minute"
        self.hint = (
            f"Zoho is throttling requests. Wait {wait} before retrying, and prefer fewer, "
            "more specific calls (search instead of paging through everything)."
        )


class DailyBudgetExceeded(ZohoError):
    hint = (
        "The connector's daily Zoho API budget is used up (it is shared with the merchant's other "
        "integrations). Do not retry today; tell the user."
    )


class ZohoUnavailable(ZohoError):
    hint = "Zoho is temporarily unavailable. Retry later; do not loop."
