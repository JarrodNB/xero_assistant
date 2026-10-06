"""Purpose: Call the Xero Accounting API with a demo-company custom connection.

Public API:
- XeroClient
- XeroApiError
"""

import time
from typing import Any

import httpx

TOKEN_URL = "https://identity.xero.com/connect/token"
API_ROOT = "https://api.xero.com/api.xro/2.0"
SCOPES = "accounting.invoices accounting.contacts accounting.settings"


class XeroApiError(Exception):
    """Xero rejected a token or accounting request."""

    def __init__(self, status_code: int, message: str) -> None:
        """Store the HTTP status and a short response body."""
        self.status_code = status_code
        self.message = message
        super().__init__(message)


class XeroClient:
    """Custom-connection client for one Xero organisation."""

    def __init__(self, client_id: str, client_secret: str, http: httpx.AsyncClient | None = None) -> None:
        """Store credentials and an optional HTTP client for tests."""
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.AsyncClient(timeout=30)
        self._owns_http = http is None
        self._access_token = ""
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

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send one accounting request with a fresh or cached access token."""
        token = await self._token()
        response = await self._http.request(
            method,
            f"{API_ROOT}{path}",
            params=params,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
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

    async def _token(self) -> str:
        """Return a cached client-credentials access token."""
        if self._access_token and self._token_expiry > time.time() + 30:
            return self._access_token
        if not self._client_id or not self._client_secret:
            raise XeroApiError(500, "Xero client id and client secret are not configured.")
        response = await self._http.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "scope": SCOPES},
            auth=(self._client_id, self._client_secret),
        )
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, "Xero refused the client-credentials token request.")
        body = response.json()
        self._access_token = str(body["access_token"])
        self._token_expiry = time.time() + int(body.get("expires_in", 1800))
        return self._access_token
