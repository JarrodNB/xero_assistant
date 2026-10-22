"""Purpose: Build the in-process MCP server from one module per domain tool.

Public API:
- REPORT_TOOL_NAMES
- READ_TOOL_NAMES
- MCP_TOOL_NAMES
- build_mcp_server
"""

from fastmcp import FastMCP

from app.mcp_server.tools import (
    register_compare_invoice_totals,
    register_find_contacts,
    register_find_invoices,
    register_get_invoice,
    register_propose_action,
    register_summarize_invoices,
)

from app.mcp_server.tools.reports import register_report_tools

REPORT_TOOL_NAMES = frozenset({"compare_profit_and_loss", "compare_balance_sheets"})

READ_TOOL_NAMES = frozenset(
    {
        "find_contacts",
        "find_invoices",
        "get_invoice",
        "summarize_invoices",
        "compare_invoice_totals",
    }
)
MCP_TOOL_NAMES = READ_TOOL_NAMES | REPORT_TOOL_NAMES | {"propose_action"}


def build_mcp_server() -> FastMCP:
    """Register each domain tool on a new in-process MCP server."""
    server = FastMCP("xero-assistant")
    register_find_contacts(server)
    register_find_invoices(server)
    register_get_invoice(server)
    register_summarize_invoices(server)
    register_compare_invoice_totals(server)
    register_propose_action(server)
    register_report_tools(server)
    return server
