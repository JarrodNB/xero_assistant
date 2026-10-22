"""Purpose: Register the read-only compare_profit_and_loss MCP boundary.

Public API:
- register_compare_profit_and_loss
"""

from fastmcp import FastMCP
from app.mcp_server.tools.reports.payload import ReportHandoff, ProtectedReportEvidence, report_evidence


def register_compare_profit_and_loss(server: FastMCP) -> None:
    """Expose bounded context evidence or a value-free Performance handoff."""
    @server.tool
    async def compare_profit_and_loss() -> ReportHandoff | ProtectedReportEvidence:
        """Read fresh bound profit-and-loss evidence or offer a Performance handoff.

        When to use: company profit/revenue comparisons and explanations of report movements.
        When not to use: invoice sales totals, unpaid invoices, or accounting writes.
        Parameters: none; dates and account must be selected in Performance. No context means navigation only.
        Example: compare_profit_and_loss(). Schema v1; bounded evidence, no amounts or raw report trees.
        """
        return report_evidence("profit_and_loss")
