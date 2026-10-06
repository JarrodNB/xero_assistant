"""Purpose: Domain packages for MCP tools.

Public API:
- register_compare_invoice_totals
- register_find_contacts
- register_find_invoices
- register_get_invoice
- register_propose_action
- register_summarize_invoices
"""

from app.mcp_server.tools.actions import register_propose_action
from app.mcp_server.tools.contacts import register_find_contacts
from app.mcp_server.tools.invoices import (
    register_compare_invoice_totals,
    register_find_invoices,
    register_get_invoice,
    register_summarize_invoices,
)

__all__ = [
    "register_compare_invoice_totals",
    "register_find_contacts",
    "register_find_invoices",
    "register_get_invoice",
    "register_propose_action",
    "register_summarize_invoices",
]
