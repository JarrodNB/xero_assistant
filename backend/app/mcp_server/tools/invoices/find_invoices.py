"""Purpose: List invoices using human-readable filters.

Public API:
- register_find_invoices
"""

from fastmcp import FastMCP

from app.errors import tool_error
from app.invoices.gateway import InvoiceServiceError
from app.invoices.records import invoice_payload
from app.mcp_server.context import parse_date, services


def register_find_invoices(server: FastMCP) -> None:
    """Register find_invoices on the MCP server."""

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
            invoices = await services().invoices.find_invoices(
                contact_name,
                status,
                parse_date(date_from),
                parse_date(date_to),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, "invoices": [invoice_payload(invoice) for invoice in invoices]}
