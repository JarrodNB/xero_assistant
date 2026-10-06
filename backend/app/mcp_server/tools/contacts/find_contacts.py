"""Purpose: Look up Xero contacts by name.

Public API:
- register_find_contacts
"""

from fastmcp import FastMCP

from app.errors import tool_error
from app.invoices.gateway import InvoiceServiceError
from app.invoices.records import contact_payload
from app.mcp_server.context import services


def register_find_contacts(server: FastMCP) -> None:
    """Register find_contacts on the MCP server."""

    @server.tool
    async def find_contacts(name: str) -> dict:
        """Find contacts by name.

        When to use: the person names a customer, or you need to know whether a contact exists before an invoice.
        When not to use: you already have an exact contact from an earlier tool result in this turn.
        Parameters: name is the full or partial contact name, for example Bob's Construction.
        Example: find_contacts(name="Bob's Construction").
        Example: find_contacts(name="Bob").
        """
        try:
            contacts = await services().invoices.find_contacts(name)
        except InvoiceServiceError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        return {"ok": True, "contacts": [contact_payload(contact) for contact in contacts]}
