"""Purpose: Current-turn services and date parsing shared by the MCP tools.

Public API:
- services
- parse_date
- require_date
"""

from datetime import date

from app.invoices.gateway import InvoiceServiceError
from app.runtime import AppServices, current_services


def services() -> AppServices:
    """Return the services bound to the current chat turn."""
    bound = current_services.get()
    if bound is None:
        raise InvoiceServiceError(
            "Invoice tools are unavailable",
            "This turn has no invoice service.",
            False,
            "Wait for the person to send the message again.",
        )
    return bound


def parse_date(value: str | None) -> date | None:
    """Parse an optional ISO date."""
    if value is None or value == "":
        return None
    return date.fromisoformat(value)


def require_date(value: str) -> date:
    """Parse a required ISO date."""
    return date.fromisoformat(value)
