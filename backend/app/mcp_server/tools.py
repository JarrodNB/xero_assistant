"""Purpose: Read-only Xero tools plus propose_action for the in-process MCP server.

Public API:
- READ_TOOL_NAMES
- build_mcp_server
"""

import json
from datetime import date

from fastmcp import FastMCP

from app.actions.payloads import parse_action, summarize_action
from app.errors import ApiError, tool_error
from app.invoices.gateway import InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import contact_payload, invoice_payload
from app.invoices.summary import comparison_payload, summary_payload
from app.runtime import current_conversation_id, current_services

READ_TOOL_NAMES = frozenset(
    {
        "find_contacts",
        "find_invoices",
        "get_invoice",
        "summarize_invoices",
        "compare_invoice_totals",
    }
)
MCP_TOOL_NAMES = READ_TOOL_NAMES | {"propose_action"}


def build_mcp_server() -> FastMCP:
    """Register the invoice tools on a new in-process MCP server."""
    server = FastMCP("xero-invoices")

    @server.tool
    async def find_contacts(name: str) -> dict:
        """Find contacts by name.

        When to use: the person names a customer, or you need to know whether a contact exists before an invoice.
        When not to use: you already have an exact contact from an earlier tool result in this turn.
        Parameters: name is the full or partial contact name, for example Bob's Construction.
        Example: find_contacts(name="Bob's Construction").
        Example: find_contacts(name="Bob").
        """
        try:
            contacts = await _services().invoices.find_contacts(name)
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        return {"ok": True, "contacts": [contact_payload(contact) for contact in contacts]}

    @server.tool
    async def find_invoices(
        contact_name: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """List invoices using human-readable filters.

        When to use: the person wants to see invoices, or you need an invoice number before an update or void.
        When not to use: you only need unpaid or overdue totals. Use summarize_invoices for totals.
        Parameters: contact_name, status (DRAFT, SUBMITTED, AUTHORISED, PAID, VOIDED), date_from and date_to as YYYY-MM-DD. All are optional.
        Example: find_invoices(status="AUTHORISED", contact_name="Bob's Construction").
        Example: find_invoices(date_from="2026-01-01", date_to="2026-03-31").
        """
        try:
            invoices = await _services().invoices.find_invoices(
                contact_name,
                status,
                _parse_date(date_from),
                _parse_date(date_to),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, "invoices": [invoice_payload(invoice) for invoice in invoices]}

    @server.tool
    async def get_invoice(invoice_number: str) -> dict:
        """Load one invoice by its invoice number.

        When to use: the person asks about a specific invoice, or you need its lines before proposing an update.
        When not to use: you only have a contact name. Use find_invoices first.
        Parameters: invoice_number is the number shown to people, such as INV-0042.
        Example: get_invoice(invoice_number="INV-0042").
        """
        try:
            invoice = await _services().invoices.get_invoice(invoice_number)
        except InvoiceNotFoundError as error:
            return tool_error(
                "Invoice does not exist",
                f"No invoice is numbered {error.invoice_number}.",
                False,
                "Use find_invoices to look up the invoice number.",
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        return {"ok": True, "invoice": invoice_payload(invoice, include_lines=True)}

    @server.tool
    async def summarize_invoices(
        contact_name: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Summarize invoice totals, including how much is unpaid or overdue.

        When to use: the person asks how much is unpaid, which invoices are overdue, or for a total over a period.
        When not to use: the person wants the individual invoices listed. Use find_invoices instead.
        Parameters: optional contact_name, status, and YYYY-MM-DD date_from and date_to. Unpaid means authorised with an amount due. Overdue means unpaid and past the due date.
        Example: summarize_invoices() for the current unpaid and overdue totals.
        Example: summarize_invoices(date_from="2026-01-01", date_to="2026-01-31").
        """
        try:
            summary = await _services().invoices.summarize_invoices(
                contact_name,
                status,
                _parse_date(date_from),
                _parse_date(date_to),
                date.today(),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, **summary_payload(summary)}

    @server.tool
    async def compare_invoice_totals(
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
    ) -> dict:
        """Compare recognised invoice totals for two date ranges.

        When to use: the person asks whether revenue is up or down between two periods.
        When not to use: the person wants the current unpaid balance. Use summarize_invoices instead.
        Parameters: four YYYY-MM-DD dates. Totals include authorised and paid invoices, and exclude drafts and voided invoices.
        Example: compare_invoice_totals(period_a_start="2026-01-01", period_a_end="2026-01-31", period_b_start="2026-02-01", period_b_end="2026-02-28").
        """
        try:
            comparison = await _services().invoices.compare_invoice_totals(
                _require_date(period_a_start),
                _require_date(period_a_end),
                _require_date(period_b_start),
                _require_date(period_b_end),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, **comparison_payload(comparison)}

    @server.tool
    async def propose_action(action_type: str, payload_json: str) -> dict:
        """Store one write for a person to confirm. This does not change Xero.

        When to use: the person asked to create a contact, create an invoice, update an invoice, or void an invoice.
        When not to use: the person only asked a question, or a proposal from this turn is still waiting. Never use this to claim the write already happened.
        Parameters: action_type is create_contact, create_invoice, update_invoice, or void_invoice. payload_json is a JSON object.
        create_contact payload: {"name": "Bob's Construction", "email": "accounts@example.com"}.
        create_invoice payload: {"contact_name": "Bob's Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}]}.
        update_invoice payload: {"invoice_number": "INV-0042", "reference": "Updated"}.
        void_invoice payload: {"invoice_number": "INV-0042"}.
        Example: propose_action(action_type="create_contact", payload_json='{"name": "Bob\\'s Construction"}').
        Example: propose_action(action_type="create_invoice", payload_json='{"contact_name": "Bob\\'s Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}]}').
        """
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            return tool_error(
                "No conversation is available",
                "The proposal was not attached to a chat.",
                False,
                "Stop and wait for the person to send the request again.",
            )
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            return tool_error(
                "Action payload is not JSON",
                "payload_json must be a JSON object.",
                False,
                "Propose the action again with a JSON object in payload_json.",
            )
        if not isinstance(payload, dict):
            return tool_error(
                "Action payload is not an object",
                "payload_json must be a JSON object.",
                False,
                "Propose the action again with a JSON object.",
            )
        try:
            parse_action(action_type, payload)
            summary = summarize_action(action_type, payload)
        except ApiError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        stored = _services().actions.create_action(conversation_id, action_type, payload, summary)
        return {
            "ok": True,
            "kind": "proposed_action",
            "action_id": stored.id,
            "action_type": stored.action_type,
            "status": "pending",
            "summary": stored.summary,
            "payload": stored.payload,
        }

    return server


def _services():
    """Return the services bound to the current chat turn."""
    services = current_services.get()
    if services is None:
        raise InvoiceServiceError(
            "Invoice tools are unavailable",
            "This turn has no invoice service.",
            False,
            "Wait for the person to send the message again.",
        )
    return services


def _parse_date(value: str | None) -> date | None:
    """Parse an optional ISO date."""
    if value is None or value == "":
        return None
    return date.fromisoformat(value)


def _require_date(value: str) -> date:
    """Parse a required ISO date."""
    return date.fromisoformat(value)
