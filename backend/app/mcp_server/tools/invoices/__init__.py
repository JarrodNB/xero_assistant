"""Purpose: Invoice MCP tools.

Public API:
- register_compare_invoice_totals
- register_find_invoices
- register_get_invoice
- register_summarize_invoices
"""

from app.mcp_server.tools.invoices.compare_invoice_totals import register_compare_invoice_totals
from app.mcp_server.tools.invoices.find_invoices import register_find_invoices
from app.mcp_server.tools.invoices.get_invoice import register_get_invoice
from app.mcp_server.tools.invoices.summarize_invoices import register_summarize_invoices

__all__ = [
    "register_compare_invoice_totals",
    "register_find_invoices",
    "register_get_invoice",
    "register_summarize_invoices",
]
