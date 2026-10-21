"""Purpose: Summarize unpaid, overdue, and period invoice totals.

Public API:
- register_summarize_invoices
"""

from datetime import date

from fastmcp import FastMCP

from app.errors import tool_error
from app.invoices.gateway import InvoiceServiceError
from app.invoices.summary import summary_payload, validate_date_range
from app.invoices.schemas import InvoiceSummaryToolPayload, ToolErrorPayload
from app.mcp_server.context import parse_date, services


def register_summarize_invoices(server: FastMCP) -> None:
    """Register summarize_invoices on the MCP server."""

    @server.tool
    async def summarize_invoices(
        contact_name: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> InvoiceSummaryToolPayload | ToolErrorPayload:
        """Summarize invoice totals, including how much is unpaid or overdue.

        When to use: the person asks how much is unpaid, which invoices are overdue, or for a total over a period.
        When not to use: the person wants the individual invoices listed. Use find_invoices instead.
        Parameters: optional contact_name, status, and YYYY-MM-DD date_from and date_to. Unpaid means authorised with an amount due. Overdue means unpaid and past the due date.
        Example: summarize_invoices() for the current unpaid and overdue totals.
        Example: summarize_invoices(date_from="2026-01-01", date_to="2026-01-31").
        Result schema v2: currencies contains separate native-currency totals in code order; empty means no invoices. Never add currencies or convert. Incomplete reads return an error; narrow filters.
        """
        try:
            validate_date_range(parse_date(date_from), parse_date(date_to))
            summary = await services().invoices.summarize_invoices(
                contact_name,
                status,
                parse_date(date_from),
                parse_date(date_to),
                date.today(),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, **summary_payload(summary)}
