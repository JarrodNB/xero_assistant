"""Purpose: Store one pending write for a person to confirm.

Public API:
- register_propose_action
"""

import json

from fastmcp import FastMCP

from app.actions.payloads import parse_action, summarize_action
from app.errors import ApiError, tool_error
from app.mcp_server.context import services
from app.runtime import current_conversation_id


def register_propose_action(server: FastMCP) -> None:
    """Register propose_action on the invoice MCP server."""

    @server.tool
    async def propose_action(action_type: str, payload_json: str) -> dict:
        """Store one write for a person to confirm. This does not change Xero.

        When to use: the person asked to create a contact, create an invoice, update an invoice, or void an invoice.
        When not to use: the person only asked a question, or a proposal from this turn is still waiting. Never use this to claim the write already happened.
        Parameters: action_type is create_contact, create_invoice, update_invoice, or void_invoice. payload_json is a JSON object.
        create_contact payload: {"name": "Bob's Construction", "email": "accounts@example.com"}.
        create_invoice payload: {"contact_name": "Bob's Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}]}.
        update_invoice payload: {"invoice_number": "INV-0042", "reference": "Updated"}.
        void_invoice payload: {"invoice_number": "INV-0042"}.
        Example: propose_action(action_type="create_contact", payload_json='{"name": "Bob\\'s Construction"}').
        Example: propose_action(action_type="create_invoice", payload_json='{"contact_name": "Bob\\'s Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}]}').
        """
        conversation_id = current_conversation_id.get()
        if not conversation_id:
            return tool_error(
                "No conversation is available",
                "The proposal was not attached to a chat.",
                False,
                "Stop and wait for the person to send the request again.",
            )
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            return tool_error(
                "Action payload is not JSON",
                "payload_json must be a JSON object.",
                False,
                "Propose the action again with a JSON object in payload_json.",
            )
        if not isinstance(payload, dict):
            return tool_error(
                "Action payload is not an object",
                "payload_json must be a JSON object.",
                False,
                "Propose the action again with a JSON object.",
            )
        try:
            parse_action(action_type, payload)
            summary = summarize_action(action_type, payload)
        except ApiError as error:
            return tool_error(error.what, error.why, error.retryable, error.next_step)
        stored = services().actions.create_action(conversation_id, action_type, payload, summary)
        return {
            "ok": True,
            "kind": "proposed_action",
            "action_id": stored.id,
            "action_type": stored.action_type,
            "status": "pending",
            "summary": stored.summary,
            "payload": stored.payload,
        }
