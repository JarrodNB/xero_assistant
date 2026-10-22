"""Purpose: Call the Xero Accounting API with a stored authorisation-code grant.

Public API:
- XeroClient
- XeroApiError
- current_write_key
"""

import asyncio
import time
import uuid
from contextvars import ContextVar
from typing import Any

import httpx

from app.xero.connection_store import XeroConnection, XeroConnectionStore

TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
API_ROOT = "https://api.xero.com/api.xro/2.0"
current_write_key: ContextVar[str | None] = ContextVar("current_write_key", default=None)
current_read_tenant: ContextVar[str | None] = ContextVar("current_read_tenant", default=None)
MAX_ATTEMPTS = 3
MAX_RETRY_DELAY = 2.0


class XeroApiError(Exception):
    """Xero rejected a token or accounting request."""

    def __init__(self, status_code: int, message: str, *, outcome_unknown: bool = False) -> None:
        """Store a sanitized failure and whether an accounting write may have succeeded."""
        self.status_code = status_code
        self.message = message
        self.outcome_unknown = outcome_unknown
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
        self._refresh_lock = asyncio.Lock()

    def connected_tenant(self) -> str:
        """Read the current trusted connection identity for bounded report operations."""
        connection = self._store.load()
        if connection is None:
            raise XeroApiError(409, "Xero connection is unavailable.")
        return connection.tenant_id

    async def aclose(self) -> None:
        """Close the HTTP client when this object created it."""
        if self._owns_http:
            await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send an authorised GET request and return the JSON body."""
        return await self._request("GET", path, params=params)

    async def get_bounded(self, path: str, params: dict[str, Any] | None = None, *, max_bytes: int = 1048576) -> dict[str, Any]:
        """Read bounded decoded bytes before JSON parsing, with the usual read retries."""
        if max_bytes < 1:
            raise ValueError("Response byte limit must be positive.")
        return await self._request("GET", path, params=params, max_response_bytes=max_bytes)

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
        response = await self._send(
            "GET",
            CONNECTIONS_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, "Xero did not return a connection.")
        body = _response_json(response)
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
        max_response_bytes: int | None = None,
    ) -> dict[str, Any]:
        """Send one accounting request with a fresh or cached access token."""
        token, tenant_id = await self._access()
        expected = current_read_tenant.get()
        if expected is not None and (tenant_id != expected or self.connected_tenant() != expected):
            raise XeroApiError(409, "Xero connection changed during the report read.")
        is_write = method != "GET"
        headers = {
            "Authorization": f"Bearer {token}",
            "Xero-Tenant-Id": tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if is_write:
            headers["Idempotency-Key"] = current_write_key.get() or f"ledger-request-{uuid.uuid4()}"
        response = await self._send(
            method,
            f"{API_ROOT}{path}",
            params=params,
            json=payload,
            headers=headers,
            outcome_unknown=is_write,
            max_response_bytes=max_response_bytes,
        )
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, "Xero rejected the accounting request.", outcome_unknown=is_write and response.status_code >= 500)
        body = _response_json(response, outcome_unknown=is_write)
        if not isinstance(body, dict):
            raise XeroApiError(502, "Xero returned an invalid accounting response.", outcome_unknown=is_write)
        return body

    async def _send(self, method: str, url: str, *, outcome_unknown: bool = False, retry: bool = True, max_response_bytes: int | None = None, **kwargs: Any) -> httpx.Response:
        """Retry bounded reads or identical keyed writes without replaying OAuth grants."""
        attempts = MAX_ATTEMPTS if retry else 1
        started = time.monotonic()
        uncertain = False
        for attempt in range(attempts):
            try:
                response = (await self._bounded_response(method, url, max_response_bytes, **kwargs)
                            if max_response_bytes is not None else await self._http.request(method, url, **kwargs))
            except httpx.RequestError as error:
                uncertain = outcome_unknown
                if attempt + 1 == attempts or time.monotonic() - started > 120:
                    raise XeroApiError(503, "Xero could not be reached.", outcome_unknown=outcome_unknown) from error
                await asyncio.sleep(0.25 * 2 ** attempt)
                continue
            uncertain = uncertain or (outcome_unknown and response.status_code >= 500)
            if uncertain and response.status_code >= 400 and (response.status_code < 500 and response.status_code != 429 or attempt + 1 == attempts):
                raise XeroApiError(response.status_code, "Xero did not provide a reliable write result.", outcome_unknown=True)
            if response.status_code != 429 and response.status_code < 500:
                return response
            if attempt + 1 == attempts or time.monotonic() - started > 120:
                return response
            delay = _retry_delay(response, attempt)
            if delay is None:
                if uncertain:
                    raise XeroApiError(response.status_code, "Xero did not provide a reliable write result.", outcome_unknown=True)
                return response
            await asyncio.sleep(delay)
        raise AssertionError("Retry loop must return or raise.")

    async def _bounded_response(self, method: str, url: str, max_bytes: int, **kwargs: Any) -> httpx.Response:
        """Close the stream immediately when decoded content exceeds the read budget."""
        async with self._http.stream(method, url, **kwargs) as response:
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=16384):
                if len(content) + len(chunk) > max_bytes:
                    raise XeroApiError(413, "Xero returned a response exceeding the report size limit.")
                content.extend(chunk)
            # aiter_bytes already decoded compression; do not apply that encoding again.
            headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-encoding", "content-length"}}
            return httpx.Response(response.status_code, headers=headers, content=bytes(content), request=response.request)

    async def _access(self) -> tuple[str, str]:
        """Return a cached access token, refreshing it with the stored refresh token."""
        async with self._refresh_lock:
            return await self._refresh_access()

    async def _refresh_access(self) -> tuple[str, str]:
        """Refresh inside the lock so concurrent callers cannot race token rotation."""
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
        response = await self._send("POST", TOKEN_URL, data=data, auth=(self._client_id, self._client_secret), retry=False)
        if response.status_code >= 400:
            raise XeroApiError(response.status_code, failure)
        body = _response_json(response)
        if not isinstance(body, dict) or "access_token" not in body or "refresh_token" not in body:
            raise XeroApiError(response.status_code, "Xero did not return a refresh token.")
        return body


def _response_json(response: httpx.Response, *, outcome_unknown: bool = False) -> Any:
    """Decode JSON without exposing provider bodies to callers or the model."""
    try:
        return response.json()
    except ValueError as error:
        raise XeroApiError(502, "Xero returned invalid JSON.", outcome_unknown=outcome_unknown) from error


def _retry_delay(response: httpx.Response, attempt: int) -> float | None:
    """Honor short numeric Retry-After values and stop rather than retry too early."""
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            return None
        if not 0 <= delay <= MAX_RETRY_DELAY:
            return None
        return delay
    return 0.25 * 2 ** attempt
