"""Purpose: Call the Xero Accounting API with a stored authorisation-code grant.

Public API:
- XeroClient
- XeroApiError
"""

import time
from typing import Any

import httpx

from app.xero.connection_store import XeroConnection, XeroConnectionStore

TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_ROOT = "https://api.xero.com/api.xro/2.0"


class XeroApiError(Exception):
    """Xero rejected a token or accounting request."""

    def __init__(self, status_code: int, message: str) -> None:
        """Store the HTTP status and a short response body."""
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class XeroClient:
    """Accounting client for the organisation authorised through OAuth."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        connection_store: XeroConnectionStore,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Store credentials, the connection store, and an optional HTTP client for tests."""
        self._client_id = client_id
        self._client_secret = client_secret
        self._store = connection_store
        self._http = http or httpx.AsyncClient(timeout=30)
        self._owns_http = http is None
        self._access_token = ""
        self._tenant_id = ""
        self._token_expiry = 0.0

    async def aclose(self) -> None:
        """Close the HTTP client when this object created it."""
        if self._owns_http:
            await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an authorised GET request and return the JSON body."""
        return await self._request("GET", path, params=params)

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send an authorised POST request and return the JSON body."""
        return await self._request("POST", path, payload=payload)

    async def exchange_code(self, code: str, redirect_uri: str) -> tuple[str, str, int]:
        """Exchange an authorisation code for an access token and a refresh token."""
        body = await self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
            "Xero refused the authorisation code.",
        )
        return str(body["access_token"]), str(body["refresh_token"]), int(body.get("expires_in", 1800))

    async def connections(self, access_token: str) -> list[dict[str, Any]]:
        """Return the organisations this access token can use."""
        response = await self._http.get(
            CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, "Xero did not return a connection.")
        body = response.json()
        if not isinstance(body, list):
            raise XeroApiError(response.status_code, "Xero returned a connection list that was not a list.")
        return body

    def connect(self, connection: XeroConnection, access_token: str, expires_in: int) -> None:
        """Save a new authorisation and cache its access token."""
        if not connection.refresh_token or not connection.tenant_id:
            raise XeroApiError(409, "Xero returned no organisation.")
        self._store.save(connection)
        self._access_token = access_token
        self._tenant_id = connection.tenant_id
        self._token_expiry = time.time() + expires_in

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one accounting request with a fresh or cached access token."""
        token, tenant_id = await self._access()
        response = await self._http.request(
            method,
            f"{API_ROOT}{path}",
            params=params,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Xero-Tenant-Id": tenant_id,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, response.text[:500])
        body = response.json()
        if not isinstance(body, dict):
            raise XeroApiError(response.status_code, "Xero returned a response that was not an object.")
        return body

    async def _access(self) -> tuple[str, str]:
        """Return a cached access token, refreshing it with the stored refresh token."""
        if self._access_token and self._tenant_id and self._token_expiry > time.time() + 30:
            return self._access_token, self._tenant_id
        connection = self._store.load()
        if connection is None:
            raise XeroApiError(409, "Xero is not connected.")
        body = await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": connection.refresh_token},
            "Xero refused the refresh token.",
        )
        self._store.save(
            XeroConnection(
                refresh_token=str(body["refresh_token"]),
                tenant_id=connection.tenant_id,
                tenant_name=connection.tenant_name,
            )
        )
        self._access_token = str(body["access_token"])
        self._tenant_id = connection.tenant_id
        self._token_expiry = time.time() + int(body.get("expires_in", 1800))
        return self._access_token, self._tenant_id

    async def _token_request(self, data: dict[str, str], failure: str) -> dict[str, Any]:
        """Post a token request and return the JSON body."""
        if not self._client_id or not self._client_secret:
            raise XeroApiError(500, "Xero client id and client secret are not configured.")
        response = await self._http.post(TOKEN_URL, data=data, auth=(self._client_id, self._client_secret))
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, failure)
        body = response.json()
        if not isinstance(body, dict) or "access_token" not in body or "refresh_token" not in body:
            raise XeroApiError(response.status_code, "Xero did not return a refresh token.")
        return body
