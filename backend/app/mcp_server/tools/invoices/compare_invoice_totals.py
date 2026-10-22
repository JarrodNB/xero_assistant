"""Purpose: Compare recognised invoice totals across two date ranges.

Public API:
- register_compare_invoice_totals
"""

from fastmcp import FastMCP

from app.errors import tool_error
from app.invoices.gateway import InvoiceServiceError
from app.invoices.summary import comparison_payload, validate_date_range
from app.invoices.schemas import PeriodComparisonToolPayload, ToolErrorPayload
from app.mcp_server.context import require_date, services


def register_compare_invoice_totals(server: FastMCP) -> None:
    """Register compare_invoice_totals on the MCP server."""

    @server.tool
    async def compare_invoice_totals(
        period_a_start: str,
        period_a_end: str,
        period_b_start: str,
        period_b_end: str,
    ) -> PeriodComparisonToolPayload | ToolErrorPayload:
        """Compare recognised invoice totals for two date ranges.

        When to use: the person asks whether recognised invoice sales totals changed between two periods.
        When not to use: company revenue/profit or balance-sheet reporting; use compare_profit_and_loss or compare_balance_sheets. For unpaid balances use summarize_invoices.
        Parameters: four YYYY-MM-DD dates. Totals include authorised and paid invoices, and exclude drafts and voided invoices.
        Example: compare_invoice_totals(period_a_start="2026-01-01", period_a_end="2026-01-31", period_b_start="2026-02-01", period_b_end="2026-02-28").
        Result schema v2: currencies aligns native currencies in code order, with zero for a missing period; empty means no recognised invoices. Never sum currencies. Incomplete reads return an error; narrow periods.
        """
        try:
            validate_date_range(require_date(period_a_start), require_date(period_a_end))
            validate_date_range(require_date(period_b_start), require_date(period_b_end))
            comparison = await services().invoices.compare_invoice_totals(
                require_date(period_a_start),
                require_date(period_a_end),
                require_date(period_b_start),
                require_date(period_b_end),
            )
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        except ValueError as error:
            return tool_error("Date is invalid", str(error), False, "Use YYYY-MM-DD dates.")
        return {"ok": True, **comparison_payload(comparison)}
