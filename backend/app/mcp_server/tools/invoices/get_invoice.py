"""Purpose: Load one invoice by the number a person sees.

Public API:
- register_get_invoice
"""

from fastmcp import FastMCP

from app.errors import tool_error
from app.invoices.gateway import InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import invoice_payload
from app.mcp_server.context import services


def register_get_invoice(server: FastMCP) -> None:
    """Register get_invoice on the MCP server."""

    @server.tool
    async def get_invoice(invoice_number: str) -> dict:
        """Load one invoice by its invoice number.

        When to use: the person asks about a specific invoice, or you need its lines before proposing an update.
        When not to use: you only have a contact name. Use find_invoices first.
        Parameters: invoice_number is the number shown to people, such as INV-0042.
        Example: get_invoice(invoice_number="INV-0042").
        """
        try:
            invoice = await services().invoices.get_invoice(invoice_number)
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
