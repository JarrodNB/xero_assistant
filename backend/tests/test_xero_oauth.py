"""Purpose: Tests for the Xero authorisation-code flow.

Public API:
- test_start_requires_the_interviewer_session
- test_start_redirects_to_xero_with_granular_scopes
- test_callback_stores_the_demo_company
- test_callback_rejects_a_mismatched_state
- test_choose_tenant_prefers_the_demo_company
"""

import os
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.xero.oauth import SCOPES, choose_tenant
from tests.conftest import sign_in
from tests.fakes import FakeInvoiceGateway


def test_start_requires_the_interviewer_session(tmp_path) -> None:
    """A signed-out visitor is sent to the login page."""
    client = _client(tmp_path, httpx.AsyncClient())
    response = client.get("/auth/xero/start", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_start_redirects_to_xero_with_granular_scopes(tmp_path) -> None:
    """The consent URL asks for the invoice, contact, and settings scopes."""
    client = _client(tmp_path, httpx.AsyncClient())
    sign_in(client)
    response = client.get("/auth/xero/start", follow_redirects=False)
    assert response.status_code == 302
    parsed = urlparse(response.headers["location"])
    params = parse_qs(parsed.query)
    assert parsed.netloc == "login.xero.com"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["http://localhost:3001/api/xero/callback"]
    assert params["scope"] == [SCOPES]
    assert "accounting.invoices" in params["scope"][0]
    assert "offline_access" in params["scope"][0]
    assert params["state"][0]


def test_callback_stores_the_demo_company(tmp_path) -> None:
    """A matching state stores the Demo Company and its refresh token."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a token and two organisations."""
        if request.url.host == "identity.xero.com":
            assert b"authorization_code" in request.content
            return httpx.Response(
                200,
                json={"access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 1800},
            )
        assert request.headers["authorization"] == "Bearer access-1"
        return httpx.Response(
            200,
            json=[
                {"tenantId": "other", "tenantName": "Other Co"},
                {"tenantId": "demo-1", "tenantName": "Demo Company"},
            ],
        )

    client = _client(tmp_path, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    sign_in(client)
    start = client.get("/auth/xero/start", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    response = client.get("/auth/xero/callback", params={"code": "auth-code", "state": state}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/invoices?xero=connected"
    connection = client.app.state.xero_connections.load()
    assert connection.tenant_id == "demo-1"
    assert connection.tenant_name == "Demo Company"
    assert connection.refresh_token == "refresh-1"
    session = client.get("/auth/session")
    assert session.json()["xero_connected"] is True
    assert session.json()["xero_tenant_name"] == "Demo Company"


def test_callback_rejects_a_mismatched_state(tmp_path) -> None:
    """A callback with the wrong state does not store a connection."""
    client = _client(tmp_path, httpx.AsyncClient())
    sign_in(client)
    client.get("/auth/xero/start", follow_redirects=False)
    response = client.get("/auth/xero/callback", params={"code": "auth-code", "state": "nope"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/invoices?xero=denied"
    assert client.app.state.xero_connections.load() is None


def test_choose_tenant_prefers_the_demo_company() -> None:
    """The Demo Company wins when the consent screen authorised more than one organisation."""
    chosen = choose_tenant(
        [
            {"tenantId": "other", "tenantName": "Other Co"},
            {"tenantId": "demo-1", "tenantName": "Demo Company"},
        ]
    )
    assert chosen["tenantId"] == "demo-1"


def _client(tmp_path, http: httpx.AsyncClient) -> TestClient:
    """Build an API client with a scripted Xero HTTP transport."""
    settings = Settings(
        app_username="interviewer",
        app_password_hash=os.environ["APP_PASSWORD_HASH"],
        session_secret="test-session-secret",
        database_path=str(tmp_path / "app.db"),
        model="openai:gpt-4.1-mini",
        xero_client_id="client-id",
        xero_client_secret="client-secret",
        xero_redirect_uri="http://localhost:3001/api/xero/callback",
    )
    application = create_app(settings=settings, invoices=FakeInvoiceGateway(), xero_http=http)
    return TestClient(application)
