"""Purpose: One module per invoice MCP tool.

Public API:
- register_compare_invoice_totals
- register_find_contacts
- register_find_invoices
- register_get_invoice
- register_propose_action
- register_summarize_invoices
"""

from app.mcp_server.tools.compare_invoice_totals import register_compare_invoice_totals
from app.mcp_server.tools.find_contacts import register_find_contacts
from app.mcp_server.tools.find_invoices import register_find_invoices
from app.mcp_server.tools.get_invoice import register_get_invoice
from app.mcp_server.tools.propose_action import register_propose_action
from app.mcp_server.tools.summarize_invoices import register_summarize_invoices

__all__ = [
    "register_compare_invoice_totals",
    "register_find_contacts",
    "register_find_invoices",
    "register_get_invoice",
    "register_propose_action",
    "register_summarize_invoices",
]
