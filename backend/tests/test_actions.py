"""Purpose: Tests for action validation and the Xero write boundary.

Public API:
- test_create_invoice_requires_a_line
- test_missing_contact_does_not_create_one_in_xero
- test_confirm_missing_contact_does_not_write
- test_confirm_and_deny_are_separate
"""

from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.actions.executor import execute_action
from app.actions.payloads import parse_action
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.errors import ApiError
from app.invoices.records import ContactRecord, InvoiceRecord
from app.invoices.xero_service import XeroInvoiceService
from app.xero.client import XeroClient
from sqlalchemy.orm import sessionmaker

from tests.conftest import sign_in
from tests.fakes import FakeInvoiceGateway


def test_create_invoice_requires_a_line() -> None:
    """An invoice proposal without lines is rejected."""
    with pytest.raises(ApiError):
        parse_action("create_invoice", {"contact_name": "Bob's Construction", "line_items": []})


def test_unknown_action_is_rejected() -> None:
    """The model cannot propose an unsupported write."""
    with pytest.raises(ApiError):
        parse_action("delete_database", {"sql": "drop table invoices"})


@pytest.mark.asyncio
async def test_missing_contact_does_not_create_one_in_xero() -> None:
    """Creating an invoice for an unknown contact does not post a contact or an invoice."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Record accounting calls and return an empty contact search."""
        calls.append((request.method, request.url.path))
        if request.url.host == "identity.xero.com":
            return httpx.Response(200, json={"access_token": "token-123", "expires_in": 1800})
        if request.url.path.endswith("/Contacts"):
            return httpx.Response(200, json={"Contacts": []})
        return httpx.Response(200, json={"Invoices": []})

    client = XeroClient("id", "secret", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    service = XeroInvoiceService(client)
    from app.invoices.gateway import ContactNotFoundError

    with pytest.raises(ContactNotFoundError):
        await service.create_invoice(
            parse_action(
                "create_invoice",
                {
                    "contact_name": "Bob's Construction",
                    "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
                },
            )  # type: ignore[arg-type]
        )
    assert ("POST", "/api.xro/2.0/Contacts") not in calls
    assert ("POST", "/api.xro/2.0/Invoices") not in calls
    await client.aclose()


def test_confirm_missing_contact_does_not_write(api, tmp_path) -> None:
    """Confirming an invoice for a missing contact stores a failure and does not write."""
    client, fake = api
    sign_in(client)
    repository: ActionRepository = client.app.state.services.actions
    repository.ensure_conversation("chat-1")
    action = repository.create_action(
        "chat-1",
        "create_invoice",
        {
            "contact_name": "Bob's Construction",
            "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
        },
        "Create an authorised invoice for Bob's Construction for 55.00.",
    )
    response = client.post(f"/actions/{action.id}/confirm")
    assert response.status_code == 409
    assert response.json()["what"] == "Contact does not exist"
    assert fake.write_calls == []
    stored = repository.get_action(action.id)
    assert stored is not None
    assert stored.status == "failed"


def test_confirm_and_deny_are_separate(api) -> None:
    """Confirm writes once, and deny never writes."""
    client, fake = api
    sign_in(client)
    fake.contacts.append(ContactRecord(name="Bob's Construction"))
    repository = client.app.state.services.actions
    repository.ensure_conversation("chat-1")
    create = repository.create_action(
        "chat-1",
        "create_invoice",
        {
            "contact_name": "Bob's Construction",
            "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
        },
        "Create an authorised invoice for Bob's Construction for 55.00.",
    )
    denied = repository.create_action(
        "chat-1",
        "void_invoice",
        {"invoice_number": "INV-1001"},
        "Void invoice INV-1001.",
    )
    confirmed = client.post(f"/actions/{create.id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "executed"
    assert confirmed.json()["invoice"]["contact_name"] == "Bob's Construction"
    assert fake.write_calls == ["create_invoice"]
    denied_response = client.post(f"/actions/{denied.id}/deny")
    assert denied_response.status_code == 200
    assert denied_response.json()["status"] == "denied"
    assert fake.write_calls == ["create_invoice"]


def test_ui_save_also_refuses_to_create_a_missing_contact(api) -> None:
    """The invoice form cannot create a contact as a side effect of saving."""
    client, fake = api
    sign_in(client)
    response = client.post(
        "/invoices",
        json={
            "contact_name": "Bob's Construction",
            "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
        },
    )
    assert response.status_code == 409
    assert fake.write_calls == []
    created = client.post("/contacts", json={"name": "Bob's Construction"})
    assert created.status_code == 200
    saved = client.post(
        "/invoices",
        json={
            "contact_name": "Bob's Construction",
            "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["invoice"]["total"] == 55
    assert fake.write_calls == ["create_contact", "create_invoice"]


def test_token_request_does_not_send_a_tenant_header() -> None:
    """Custom connections authenticate with the client secret and no tenant header."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture the accounting request headers and return no invoices."""
        if "identity.xero.com" in str(request.url):
            return httpx.Response(200, json={"access_token": "token-123", "expires_in": 1800})
        seen["authorization"] = request.headers["authorization"]
        seen["tenant"] = request.headers.get("xero-tenant-id", "")
        return httpx.Response(200, json={"Invoices": []})

    import asyncio

    async def run() -> None:
        """Perform one invoice read."""
        client = XeroClient("id", "secret", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        service = XeroInvoiceService(client)
        invoices = await service.find_invoices(None, None, None, None)
        assert invoices == []
        await client.aclose()

    asyncio.run(run())
    assert seen["authorization"] == "Bearer token-123"
    assert seen["tenant"] == ""
    assert "secret" not in seen["authorization"]
