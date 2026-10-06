"""Purpose: Start and finish the Xero authorisation-code flow.

Public API:
- router
"""

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.xero.client import XeroApiError, XeroClient
from app.xero.connection_store import XeroConnection
from app.xero.oauth import authorize_url, choose_tenant

router = APIRouter(tags=["xero"])


def _signed_in(request: Request) -> bool:
    """Return whether the interviewer session cookie is present."""
    settings: Settings = request.app.state.settings
    return request.session.get("user") == settings.app_username


@router.get("/auth/xero/start")
def start_xero_oauth(request: Request) -> RedirectResponse:
    """Send the browser to Xero so someone can authorise the Demo Company."""
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=302)
    settings: Settings = request.app.state.settings
    state = secrets.token_urlsafe(32)
    request.session["xero_oauth_state"] = state
    return RedirectResponse(
        authorize_url(settings.xero_client_id, settings.xero_redirect_uri, state),
        status_code=302,
    )


@router.get("/auth/xero/callback")
async def finish_xero_oauth(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Exchange the authorisation code and store the Demo Company tenant."""
    if not _signed_in(request):
        return RedirectResponse("/login", status_code=302)
    expected = str(request.session.pop("xero_oauth_state", "") or "")
    if error or not code or not state or not expected or not secrets.compare_digest(state, expected):
        return RedirectResponse("/invoices?xero=denied", status_code=302)
    settings: Settings = request.app.state.settings
    client: XeroClient = request.app.state.xero
    try:
        access_token, refresh_token, expires_in = await client.exchange_code(code, settings.xero_redirect_uri)
        tenant = choose_tenant(await client.connections(access_token))
        client.connect(
            XeroConnection(
                refresh_token=refresh_token,
                tenant_id=str(tenant.get("tenantId") or ""),
                tenant_name=str(tenant.get("tenantName") or ""),
            ),
            access_token,
            expires_in,
        )
    except XeroApiError:
        return RedirectResponse("/invoices?xero=failed", status_code=302)
    return RedirectResponse("/invoices?xero=connected", status_code=302)
