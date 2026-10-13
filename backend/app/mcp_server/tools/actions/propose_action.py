"""Purpose: Store one pending write for a person to confirm.

Public API:
- register_propose_action
"""

import json

from fastmcp import FastMCP

from app.actions.payloads import parse_action, summarize_action
from app.actions.chat_updates import resolve_chat_update
from app.errors import ApiError, tool_error
from app.mcp_server.context import services
from app.runtime import current_conversation_id


def register_propose_action(server: FastMCP) -> None:
    """Register propose_action on the MCP server."""

    @server.tool
    async def propose_action(action_type: str, payload_json: str) -> dict:
        """Store one write for a person to confirm. This does not change Xero.

        When to use: the person asked to create a contact, create an invoice, update an invoice, or void an invoice, and required details are known. Propose immediately even when optional fields are omitted.
        When not to use: the person only asked a question, required details are missing or ambiguous, or a proposal from this turn is still waiting. Never use this to claim the write already happened.
        Parameters: action_type is create_contact, create_invoice, update_invoice, or void_invoice. payload_json is a JSON object.
        create_contact payload: {"name": "Bob's Construction", "email": "accounts@example.com"}. Name is required; email is optional. Preserve a supplied email and omit it otherwise without asking a separate question.
        create_invoice payload: {"contact_name": "Bob's Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}], "reference": "PO-9", "due_date": "2026-10-21"}. Contact and line items are required. Reference and due_date are independently optional: preserve supplied values and omit missing values without a separate question. A blank due date means 14 days from today. An invoice has at most 100 lines and a pre-tax subtotal at most 999999999999.99. Quantity is positive, at most 99999999.9999, and has at most four decimal places. Unit amount is positive, at most 999999999999.99, and has at most two decimal places. If a requested value exceeds a limit, explain the limit and ask for a smaller value instead of proposing.
        update_invoice payload: {"invoice_number": "INV-0042", "reference": "Updated"}.
        For line edits, first read get_invoice. Supply the complete remaining line_items list. Each existing line includes original_line with its exact original description, quantity, and unit_amount, plus the desired description, quantity, and unit_amount. Omit original_line only for a new line. List removed original values in removed_lines. Every existing line must be kept once or explicitly removed. Never supply or invent internal ids; duplicate original values require the invoice editor. Example line: {"original_line": {"description": "Labour", "quantity": 1, "unit_amount": 55}, "description": "Labour", "quantity": 2, "unit_amount": 55}.
        void_invoice payload: {"invoice_number": "INV-0042"}.
        Example: propose_action(action_type="create_contact", payload_json='{"name": "Bob\\'s Construction", "email": "accounts@example.com"}').
        Example: propose_action(action_type="create_invoice", payload_json='{"contact_name": "Bob\\'s Construction", "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}], "reference": "PO-9", "due_date": "2026-10-21"}').
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
            visible_payload = payload
            if action_type == "update_invoice":
                payload = await resolve_chat_update(payload, services().invoices)
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
            "payload": visible_payload,
        }
