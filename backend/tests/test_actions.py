"""Purpose: Tests for action validation and the Xero write boundary.

Public API:
- test_create_invoice_requires_a_line
- test_missing_contact_does_not_create_one_in_xero
- test_confirm_missing_contact_does_not_write
- test_confirm_and_deny_are_separate
- test_confirm_contact_stores_email
- test_confirm_blank_email_leaves_email_unset
- test_confirm_invoice_applies_reference_and_due_date
- test_confirm_cannot_change_required_fields
- test_confirm_rejects_an_invalid_due_date
- test_system_prompt_asks_for_optional_create_fields
- test_list_contacts_returns_name_and_email
- test_list_contacts_pages_until_a_short_page
"""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.actions.executor import execute_action
from app.actions.payloads import parse_action
from app.chat.prompt import SYSTEM_PROMPT
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.errors import ApiError
from app.invoices.records import ContactRecord, InvoiceRecord
from app.invoices.xero_service import XeroInvoiceService
from app.xero.client import XeroClient
from app.xero.connection_store import XeroConnection, XeroConnectionStore
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
            return httpx.Response(
                200,
                json={"access_token": "token-123", "refresh_token": "refresh-2", "expires_in": 1800},
            )
        if request.url.path.endswith("/Contacts"):
            return httpx.Response(200, json={"Contacts": []})
        return httpx.Response(200, json={"Invoices": []})

    client = _connected_client(handler)
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


def test_confirm_contact_stores_email(api) -> None:
    """A confirm body can add an email to a contact proposal."""
    client, fake = api
    sign_in(client)
    repository: ActionRepository = client.app.state.services.actions
    repository.ensure_conversation("chat-1")
    action = repository.create_action("chat-1", "create_contact", {"name": "Ada"}, "Create contact Ada.")
    response = client.post(f"/actions/{action.id}/confirm", json={"email": " ada@example.com "})
    assert response.status_code == 200
    body = response.json()
    assert body["contact"]["email"] == "ada@example.com"
    assert body["summary"] == "Create contact Ada with email ada@example.com."
    assert fake.write_calls == ["create_contact"]
    assert fake.contacts[-1].email == "ada@example.com"
    stored = repository.get_action(action.id)
    assert stored is not None
    assert stored.payload["email"] == "ada@example.com"
    assert stored.summary == body["summary"]


def test_confirm_blank_email_leaves_email_unset(api) -> None:
    """A blank email override does not store an email."""
    client, fake = api
    sign_in(client)
    repository: ActionRepository = client.app.state.services.actions
    repository.ensure_conversation("chat-1")
    action = repository.create_action("chat-1", "create_contact", {"name": "Ada"}, "Create contact Ada.")
    response = client.post(f"/actions/{action.id}/confirm", json={"email": "  "})
    assert response.status_code == 200
    assert response.json()["contact"]["email"] is None
    assert response.json()["summary"] == "Create contact Ada."
    assert fake.contacts[-1].email is None
    stored = repository.get_action(action.id)
    assert stored is not None
    assert stored.payload["email"] is None


def test_confirm_invoice_applies_reference_and_due_date(api) -> None:
    """A confirm body can set an invoice reference and due date."""
    client, fake = api
    sign_in(client)
    fake.contacts.append(ContactRecord(name="Bob's Construction"))
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
    response = client.post(
        f"/actions/{action.id}/confirm",
        json={"reference": " PO-9 ", "due_date": "2026-11-01"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["invoice"]["reference"] == "PO-9"
    assert body["invoice"]["due_date"] == "2026-11-01"
    assert body["summary"] == (
        "Create an authorised invoice for Bob's Construction for 55.00 with reference PO-9 and due 2026-11-01."
    )
    stored = repository.get_action(action.id)
    assert stored is not None
    assert stored.payload["reference"] == "PO-9"
    assert stored.payload["due_date"] == "2026-11-01"


def test_confirm_cannot_change_required_fields(api) -> None:
    """Confirm refuses to rewrite required fields such as the contact name."""
    client, fake = api
    sign_in(client)
    repository: ActionRepository = client.app.state.services.actions
    repository.ensure_conversation("chat-1")
    contact = repository.create_action("chat-1", "create_contact", {"name": "Ada"}, "Create contact Ada.")
    response = client.post(
        f"/actions/{contact.id}/confirm",
        json={"name": "Other", "email": "ada@example.com"},
    )
    assert response.status_code == 422
    assert response.json()["what"] == "Confirm cannot change required fields"
    assert fake.write_calls == []
    stored = repository.get_action(contact.id)
    assert stored is not None
    assert stored.status == "pending"
    assert stored.payload == {"name": "Ada"}
    invoice = repository.create_action(
        "chat-1",
        "create_invoice",
        {
            "contact_name": "Bob's Construction",
            "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
        },
        "Create an authorised invoice for Bob's Construction for 55.00.",
    )
    blocked = client.post(f"/actions/{invoice.id}/confirm", json={"contact_name": "Other Co"})
    assert blocked.status_code == 422
    assert fake.write_calls == []
    stored_invoice = repository.get_action(invoice.id)
    assert stored_invoice is not None
    assert stored_invoice.status == "pending"
    assert stored_invoice.payload["contact_name"] == "Bob's Construction"


def test_confirm_rejects_an_invalid_due_date(api) -> None:
    """An invalid due date leaves the proposal pending."""
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
    response = client.post(f"/actions/{action.id}/confirm", json={"due_date": "tomorrow"})
    assert response.status_code == 422
    assert fake.write_calls == []
    stored = repository.get_action(action.id)
    assert stored is not None
    assert stored.status == "pending"
    assert "due_date" not in stored.payload


def test_system_prompt_asks_for_optional_create_fields() -> None:
    """The chat agent is told to ask for optional create fields before proposing."""
    text = SYSTEM_PROMPT.casefold()
    assert "ask once whether they want an email" in text
    assert "reference" in text
    assert "due date" in text
    assert "14 days" in text
    assert "skip" in text


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


def test_list_contacts_returns_name_and_email(api) -> None:
    """The contacts page can list every contact or filter by name."""
    client, fake = api
    sign_in(client)
    fake.contacts.append(ContactRecord(name="Juvy", email="juvy@yopmail.com"))
    fake.contacts.append(ContactRecord(name="Bob's Construction", email=None))
    listed = client.get("/contacts")
    assert listed.status_code == 200
    assert listed.json()["contacts"] == [
        {"name": "Juvy", "email": "juvy@yopmail.com"},
        {"name": "Bob's Construction", "email": None},
    ]
    filtered = client.get("/contacts", params={"name": "juv"})
    assert filtered.status_code == 200
    assert filtered.json()["contacts"] == [{"name": "Juvy", "email": "juvy@yopmail.com"}]


@pytest.mark.asyncio
async def test_list_contacts_pages_until_a_short_page() -> None:
    """Contact listing follows Xero pages and stops on a short page."""
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return a full page, then one contact."""
        if "identity.xero.com" in str(request.url):
            return httpx.Response(
                200,
                json={"access_token": "token-123", "refresh_token": "refresh-2", "expires_in": 1800},
            )
        page = int(request.url.params.get("page", "1"))
        pages.append(page)
        count = 100 if page == 1 else 1
        contacts = [
            {"Name": f"Contact {page}-{index}", "EmailAddress": f"c{page}-{index}@example.com"}
            for index in range(count)
        ]
        return httpx.Response(200, json={"Contacts": contacts})

    client = _connected_client(handler)
    service = XeroInvoiceService(client)
    contacts = await service.list_contacts()
    await client.aclose()
    assert pages == [1, 2]
    assert len(contacts) == 101
    assert contacts[0].name == "Contact 1-0"
    assert contacts[0].email == "c1-0@example.com"


def test_accounting_request_sends_the_stored_tenant() -> None:
    """Invoice reads use the tenant saved during the OAuth callback."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        """Capture the accounting request headers and return no invoices."""
        if "identity.xero.com" in str(request.url):
            return httpx.Response(
                200,
                json={"access_token": "token-123", "refresh_token": "refresh-2", "expires_in": 1800},
            )
        seen["authorization"] = request.headers["authorization"]
        seen["tenant"] = request.headers.get("xero-tenant-id", "")
        return httpx.Response(200, json={"Invoices": []})

    import asyncio

    store = _MemoryStore(XeroConnection("refresh-1", "tenant-1", "Demo Company"))

    async def run() -> None:
        """Perform one invoice read."""
        client = XeroClient("id", "secret", store, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        service = XeroInvoiceService(client)
        invoices = await service.find_invoices(None, None, None, None)
        assert invoices == []
        await client.aclose()

    asyncio.run(run())
    assert seen["authorization"] == "Bearer token-123"
    assert seen["tenant"] == "tenant-1"
    assert "secret" not in seen["authorization"]
    assert store.connection is not None
    assert store.connection.refresh_token == "refresh-2"


def _connected_client(handler: Callable[[httpx.Request], httpx.Response]) -> XeroClient:
    """Build a client that already has a Demo Company refresh token."""
    store = _MemoryStore(XeroConnection("refresh-1", "tenant-1", "Demo Company"))
    return XeroClient("id", "secret", store, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


class _MemoryStore(XeroConnectionStore):
    """In-memory stand-in that skips SQLite."""

    def __init__(self, connection: XeroConnection) -> None:
        """Start from a connection that tests can refresh."""
        self.connection: XeroConnection | None = connection

    def load(self) -> XeroConnection | None:
        """Return the in-memory connection."""
        return self.connection

    def save(self, connection: XeroConnection) -> None:
        """Replace the in-memory connection."""
        self.connection = connection
