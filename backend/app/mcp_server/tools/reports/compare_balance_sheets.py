"""Purpose: Register the read-only compare_balance_sheets MCP boundary.

Public API:
- register_compare_balance_sheets
"""

from fastmcp import FastMCP
from app.mcp_server.tools.reports.payload import ReportHandoff, ProtectedReportEvidence, report_evidence


def register_compare_balance_sheets(server: FastMCP) -> None:
    """Expose bounded context evidence or a value-free Performance handoff."""
    @server.tool
    async def compare_balance_sheets() -> ReportHandoff | ProtectedReportEvidence:
        """Read fresh bound financial-position evidence or offer a Performance handoff.

        When to use: assets, liabilities, equity, or dated position comparisons.
        When not to use: period profit, cash-flow attribution, invoice totals, or accounting writes.
        Parameters: none; as-of dates and account must be selected in Performance. No context means navigation only.
        Example: compare_balance_sheets(). Schema v1; bounded evidence, no amounts or raw report trees.
        """
        return report_evidence("balance_sheet")
