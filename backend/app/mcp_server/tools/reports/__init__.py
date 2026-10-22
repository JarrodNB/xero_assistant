"""Purpose: Register financial-report MCP tools separately from invoice tools.

Public API:
- register_report_tools
"""

from fastmcp import FastMCP
from app.mcp_server.tools.reports.compare_profit_and_loss import register_compare_profit_and_loss
from app.mcp_server.tools.reports.compare_balance_sheets import register_compare_balance_sheets


def register_report_tools(server: FastMCP) -> None:
    """Register the two versioned read-only report boundaries."""
    register_compare_profit_and_loss(server)
    register_compare_balance_sheets(server)
