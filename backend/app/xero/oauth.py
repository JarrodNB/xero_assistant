"""Purpose: Build the Xero authorisation URL and pick a tenant.

Public API:
- SCOPES
- authorize_url
- choose_tenant
"""

from typing import Any
from urllib.parse import quote, urlencode

from app.xero.client import XeroApiError

AUTHORIZE_URL = "https://login.xero.com/identity/connect/authorize"
SCOPES = "openid profile email offline_access accounting.invoices accounting.contacts accounting.settings accounting.reports.profitandloss.read accounting.reports.balancesheet.read"


def authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Return the Xero consent URL for the authorisation-code grant."""
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
        },
        quote_via=quote,
    )
    return f"{AUTHORIZE_URL}?{query}"


def choose_tenant(connections: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer the Demo Company when Xero returns more than one organisation."""
    if not connections:
        raise XeroApiError(409, "Xero returned no organisation.")
    for connection in connections:
        name = str(connection.get("tenantName") or "")
        if "demo" in name.casefold():
            return connection
    return connections[0]
