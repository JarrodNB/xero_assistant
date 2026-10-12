"""Purpose: Regressions for concurrent, interrupted, and repeated human-confirmed writes.

Public API:
- test_confirmation_race_freezes_payload_and_blocks_denial
- test_deny_before_confirm_never_writes
- test_unknown_outcome_is_not_replayed
- test_execution_deadline_quarantines_the_action
- test_cancelled_execution_is_not_replayed
- test_persistence_failure_does_not_replay_a_successful_write
- test_stale_claim_survives_restart_without_replay
- test_editor_request_ids_deduplicate_writes
- test_editor_id_cannot_change_payload_or_operation
- test_editor_unknown_receipt_cannot_be_replayed
- test_xero_retries_use_one_idempotency_key
- test_xero_transport_and_json_failures_are_sanitized
- test_xero_does_not_retry_before_long_retry_after
- test_oauth_grants_are_not_automatically_replayed
- test_later_rejection_cannot_erase_an_uncertain_attempt
- test_refresh_rotation_is_serialized
- test_failure_recording_error_keeps_the_durable_claim
"""

import asyncio
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from app.db.repository import ActionRepository
from app.db.schema import ProposedActionRow, create_engine_for, utcnow
from app.invoices.gateway import InvoiceServiceError
from app.invoices.records import ContactRecord
from app.xero.client import XeroApiError, XeroClient, current_write_key
from app.xero.connection_store import XeroConnection, XeroConnectionStore
from tests.conftest import PASSWORD, USERNAME, sign_in


def _proposal(client):
    """Persist a contact proposal without involving a model or Xero."""
    repository = client.app.state.services.actions
    repository.ensure_conversation("write-safety")
    return repository.create_action("write-safety", "create_contact", {"name": "Review Contact"}, "Create contact.")


@pytest.mark.asyncio
async def test_confirmation_race_freezes_payload_and_blocks_denial(api, monkeypatch) -> None:
    """An in-flight confirmation wins against another confirmation and a denial."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    async def create(payload):
        """Pause the external write while competing requests arrive."""
        writes.append(payload)
        entered.set()
        await release.wait()
        return ContactRecord(payload.name, payload.email)

    monkeypatch.setattr(gateway, "create_contact", create)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://testserver") as http:
        login = await http.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert login.status_code == 200
        first = asyncio.create_task(http.post(f"/actions/{action.id}/confirm", json={"email": "first@example.com"}))
        await asyncio.wait_for(entered.wait(), 2)
        try:
            repeat = await http.post(f"/actions/{action.id}/confirm", json={"email": "second@example.com"})
            denial = await http.post(f"/actions/{action.id}/deny")
            assert repeat.status_code == 200
            assert repeat.json()["status"] == "executing"
            assert denial.status_code == 409
            assert len(writes) == 1
            assert writes[0].email == "first@example.com"
        finally:
            release.set()
        result = await first
        replay = await http.post(f"/actions/{action.id}/confirm")
    assert result.status_code == 200
    assert replay.json() == result.json()
    assert len(writes) == 1
    assert client.app.state.services.actions.get_action(action.id).status == "executed"
    assert current_write_key.get() is None


def test_deny_before_confirm_never_writes(api) -> None:
    """A successfully denied action stays denied when confirmed or denied again."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    assert client.post(f"/actions/{action.id}/deny").status_code == 200
    assert client.post(f"/actions/{action.id}/confirm").status_code == 409
    assert client.post(f"/actions/{action.id}/deny").json()["status"] == "denied"
    assert gateway.write_calls == []


def test_unknown_outcome_is_not_replayed(api, monkeypatch) -> None:
    """A write without a reliable response is quarantined instead of retried later."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    writes = []

    async def uncertain(payload):
        """Simulate Xero accepting a write whose response was lost."""
        writes.append(payload)
        raise InvoiceServiceError("Execution outcome is unknown", "No final result.", False, "Check Xero.", outcome_unknown=True)

    monkeypatch.setattr(gateway, "create_contact", uncertain)
    result = client.post(f"/actions/{action.id}/confirm")
    assert result.status_code == 502
    assert result.json()["outcome_unknown"] is True
    assert client.get(f"/actions/{action.id}").json()["status"] == "unknown"
    assert client.post(f"/actions/{action.id}/confirm").json()["status"] == "unknown"
    assert len(writes) == 1


def test_execution_deadline_quarantines_the_action(api, monkeypatch) -> None:
    """A bounded execution timeout never reopens the proposal for another write."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    client.app.state.settings.action_execution_timeout_seconds = 0.02

    async def slow(_payload):
        """Wait until the application's execution deadline cancels this write."""
        await asyncio.Event().wait()

    monkeypatch.setattr(gateway, "create_contact", slow)
    response = client.post(f"/actions/{action.id}/confirm")
    assert response.status_code == 502
    assert client.get(f"/actions/{action.id}").json()["status"] == "unknown"


@pytest.mark.asyncio
async def test_cancelled_execution_is_not_replayed(api, monkeypatch) -> None:
    """Cancellation saves uncertainty and resets the request-scoped write key."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    entered = asyncio.Event()

    async def slow(_payload):
        """Signal that the write started, then await cancellation."""
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(gateway, "create_contact", slow)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://testserver") as http:
        login = await http.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert login.status_code == 200
        task = asyncio.create_task(http.post(f"/actions/{action.id}/confirm"))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert client.app.state.services.actions.get_action(action.id).status == "unknown"
    assert current_write_key.get() is None


def test_persistence_failure_does_not_replay_a_successful_write(api, monkeypatch) -> None:
    """If saving a successful response fails, the durable claim prevents repetition."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)
    repository = client.app.state.services.actions
    transition = repository.transition_action

    def broken(action_id, expected, status, result):
        """Simulate SQLite failing after the external write completed."""
        if status == "executed":
            raise OSError("private database detail")
        return transition(action_id, expected, status, result)

    monkeypatch.setattr(repository, "transition_action", broken)
    response = client.post(f"/actions/{action.id}/confirm")
    assert response.status_code == 502
    assert "private database detail" not in response.text
    assert client.post(f"/actions/{action.id}/confirm").json()["status"] == "executing"
    assert gateway.write_calls == ["create_contact"]


def test_stale_claim_survives_restart_without_replay(tmp_path) -> None:
    """Reopening an existing SQLite database preserves and quarantines abandoned writes."""
    path = str(tmp_path / "persisted.db")
    engine = create_engine_for(path)
    repository = ActionRepository(sessionmaker(bind=engine))
    repository.ensure_conversation("restart")
    action = repository.create_action("restart", "create_contact", {"name": "Review"}, "Create.")
    assert repository.claim_action(action, action.payload, action.summary) is not None
    with repository._session_factory() as session:
        session.execute(update(ProposedActionRow).where(ProposedActionRow.id == action.id).values(updated_at=utcnow() - timedelta(minutes=10)))
        session.commit()
    engine.dispose()
    reopened = create_engine_for(path)
    try:
        recovered = ActionRepository(sessionmaker(bind=reopened))
        recovered.recover_stale_action(action.id, utcnow() - timedelta(minutes=3))
        stored = recovered.get_action(action.id)
        assert stored.status == "unknown"
        assert stored.payload == action.payload
        assert recovered.claim_action(stored, stored.payload, stored.summary) is None
        assert recovered.transition_action(action.id, "executing", "executed", {}) is None
    finally:
        reopened.dispose()


@pytest.mark.parametrize("path,payload", [
    ("/contacts", {"name": "Review"}),
    ("/invoices", {"contact_name": "Review", "line_items": [{"description": "Work", "quantity": 1, "unit_amount": 10}]}),
])
def test_editor_request_ids_deduplicate_writes(api, path, payload) -> None:
    """Editor retries with one id return the first result without another gateway write."""
    client, gateway = api
    sign_in(client)
    gateway.contacts.append(ContactRecord("Review"))
    headers = {"X-Write-Id": str(uuid4())}
    first = client.post(path, json=payload, headers=headers)
    assert first.status_code == 200
    assert client.post(path, json=payload, headers=headers).json() == first.json()
    assert len(gateway.write_calls) == 1
    assert client.get("/conversations").json()["conversations"] == []


def test_editor_id_cannot_change_payload_or_operation(api) -> None:
    """A reused editor id cannot authorize a different payload or write operation."""
    client, gateway = api
    sign_in(client)
    headers = {"X-Write-Id": str(uuid4())}
    assert client.post("/contacts", json={"name": "Review"}, headers=headers).status_code == 200
    assert client.post("/contacts", json={"name": "Other"}, headers=headers).status_code == 409
    assert client.post("/invoices", json={"contact_name": "Review", "line_items": [{"description": "Work", "quantity": 1, "unit_amount": 10}]}, headers=headers).status_code == 409
    assert client.post("/contacts", json={"name": "Review"}, headers={"X-Write-Id": "invalid"}).status_code == 422
    assert gateway.write_calls == ["create_contact"]


def test_editor_unknown_receipt_cannot_be_replayed(api, monkeypatch) -> None:
    """Editor uncertainty remains durable across repeat submissions with the same id."""
    client, gateway = api
    sign_in(client)
    calls = []

    async def uncertain(payload):
        """Lose the response to a simulated accepted contact write."""
        calls.append(payload)
        raise InvoiceServiceError("Unknown", "Lost response.", False, "Check Xero.", outcome_unknown=True)

    monkeypatch.setattr(gateway, "create_contact", uncertain)
    headers = {"X-Write-Id": str(uuid4())}
    for _ in range(2):
        result = client.post("/contacts", json={"name": "Review"}, headers=headers)
        assert result.status_code == 502
        assert result.json()["outcome_unknown"] is True
    assert len(calls) == 1


def _xero(tmp_path, handler):
    """Build a connected Xero client against a mock HTTP transport."""
    engine = create_engine_for(str(tmp_path / "xero.db"))
    store = XeroConnectionStore(sessionmaker(bind=engine))
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = XeroClient("client", "secret", store, http)
    client.connect(XeroConnection("refresh", "tenant", "Demo"), "access", 1800)
    return client, http, engine


@pytest.mark.asyncio
async def test_xero_retries_use_one_idempotency_key(tmp_path) -> None:
    """Retries of a transient write keep exactly the same key and JSON body."""
    requests = []

    def handler(request):
        """Fail one write, then replay its successful response."""
        requests.append(request)
        return httpx.Response(503 if len(requests) == 1 else 200, json={"Contacts": []}, headers={"Retry-After": "0"})

    client, http, engine = _xero(tmp_path, handler)
    token = current_write_key.set("ledger-action-test")
    try:
        await client.post("/Contacts", {"Contacts": [{"Name": "Review"}]})
        assert len(requests) == 2
        assert {request.headers["Idempotency-Key"] for request in requests} == {"ledger-action-test"}
        assert requests[0].content == requests[1].content
    finally:
        current_write_key.reset(token)
        await http.aclose()
        engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,malformed", [("GET", False), ("POST", False), ("POST", True)])
async def test_xero_transport_and_json_failures_are_sanitized(tmp_path, method, malformed) -> None:
    """Provider errors expose no raw response or transport detail and label write uncertainty."""
    requests = []

    def handler(request):
        """Return malformed JSON or raise a connection error containing private detail."""
        requests.append(request)
        if malformed:
            return httpx.Response(200, text="private response detail")
        raise httpx.ConnectError("private transport detail", request=request)

    client, http, engine = _xero(tmp_path, handler)
    try:
        with pytest.raises(XeroApiError) as raised:
            if method == "GET":
                await client.get("/Contacts")
            else:
                await client.post("/Contacts", {"Contacts": []})
        assert raised.value.outcome_unknown is (method == "POST")
        assert "private" not in raised.value.message
        assert len(requests) == (1 if malformed else 3)
        if method == "POST":
            assert len({request.headers["Idempotency-Key"] for request in requests}) == 1
    finally:
        await http.aclose()
        engine.dispose()


@pytest.mark.asyncio
async def test_xero_does_not_retry_before_long_retry_after(tmp_path) -> None:
    """A long server cooldown is returned to the caller without retrying early."""
    calls = []

    def handler(request):
        """Rate limit the client for longer than the bounded retry budget."""
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"}, json={})

    client, http, engine = _xero(tmp_path, handler)
    try:
        with pytest.raises(XeroApiError) as raised:
            await client.get("/Contacts")
        assert raised.value.status_code == 429
        assert len(calls) == 1
    finally:
        await http.aclose()
        engine.dispose()


@pytest.mark.asyncio
async def test_oauth_grants_are_not_automatically_replayed(tmp_path) -> None:
    """A lost token response does not repeat a single-use authorization grant."""
    calls = []

    def handler(request):
        """Lose the token exchange response after recording the request."""
        calls.append(request)
        raise httpx.ReadTimeout("private detail", request=request)

    client, http, engine = _xero(tmp_path, handler)
    try:
        with pytest.raises(XeroApiError):
            await client.exchange_code("code", "http://localhost/callback")
        assert len(calls) == 1
    finally:
        await http.aclose()
        engine.dispose()


@pytest.mark.asyncio
async def test_later_rejection_cannot_erase_an_uncertain_attempt(tmp_path) -> None:
    """Rate limiting after a lost write response still leaves its outcome unknown."""
    calls = []

    def handler(request):
        """Lose the first response, then reject a retry during rate limiting."""
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("lost response", request=request)
        return httpx.Response(429, headers={"Retry-After": "60"}, json={})

    client, http, engine = _xero(tmp_path, handler)
    try:
        with pytest.raises(XeroApiError) as raised:
            await client.post("/Contacts", {"Contacts": []})
        assert raised.value.outcome_unknown is True
        assert len(calls) == 2
    finally:
        await http.aclose()
        engine.dispose()


@pytest.mark.asyncio
async def test_refresh_rotation_is_serialized(tmp_path) -> None:
    """Concurrent API reads refresh the single stored token only once."""
    token_calls = []

    async def handler(request):
        """Pause a token refresh long enough for a second caller to arrive."""
        if request.url.host == "identity.xero.com":
            token_calls.append(request)
            await asyncio.sleep(0.02)
            return httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 1800})
        assert request.headers["Authorization"] == "Bearer new-access"
        return httpx.Response(200, json={"Contacts": []})

    client, http, engine = _xero(tmp_path, handler)
    client._token_expiry = 0
    try:
        await asyncio.gather(client.get("/Contacts"), client.get("/Contacts"))
        assert len(token_calls) == 1
        assert client._store.load().refresh_token == "new-refresh"
    finally:
        await http.aclose()
        engine.dispose()


def test_failure_recording_error_keeps_the_durable_claim(api, monkeypatch) -> None:
    """A database failure during error handling returns sanitized uncertainty without reopening a write."""
    client, gateway = api
    sign_in(client)
    action = _proposal(client)

    async def rejected(_payload):
        """Simulate a definite business rejection before a usable result."""
        raise InvoiceServiceError("Rejected", "Invalid contact.", False, "Check contact.")

    def broken(*_args):
        """Prevent final outcome persistence without changing the existing claim."""
        raise OSError("private persistence detail")

    monkeypatch.setattr(gateway, "create_contact", rejected)
    monkeypatch.setattr(client.app.state.services.actions, "transition_action", broken)
    result = client.post(f"/actions/{action.id}/confirm")
    assert result.status_code == 502
    assert result.json()["outcome_unknown"] is True
    assert "private persistence detail" not in result.text
    assert client.post(f"/actions/{action.id}/confirm").json()["status"] == "executing"
