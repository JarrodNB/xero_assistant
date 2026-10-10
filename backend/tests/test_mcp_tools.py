"""Purpose: Assert the MCP server exposes reads and propose_action only.

Public API:
- test_mcp_tool_list_has_no_xero_writes
- test_propose_action_does_not_write_to_xero
- test_propose_action_rejects_an_oversized_chat_amount
"""

import json

import pytest
from fastmcp import Client

from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.mcp_server.server import MCP_TOOL_NAMES, build_mcp_server
from app.runtime import AppServices, current_conversation_id, current_services
from sqlalchemy.orm import sessionmaker

from tests.fakes import FakeInvoiceGateway


@pytest.mark.asyncio
async def test_mcp_tool_list_has_no_xero_writes() -> None:
    """The model cannot see a tool that writes to Xero."""
    server = build_mcp_server()
    async with Client(server) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert names == set(MCP_TOOL_NAMES)
    for forbidden in ("create_contact", "create_invoice", "update_invoice", "void_invoice", "query_database"):
        assert forbidden not in names
    for tool in tools:
        description = tool.description or ""
        assert "When to use" in description
        assert "When not to use" in description
        assert "Example:" in description


@pytest.mark.asyncio
async def test_propose_action_does_not_write_to_xero(tmp_path) -> None:
    """propose_action stores a pending row and leaves the invoice gateway untouched."""
    fake = FakeInvoiceGateway()
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(tmp_path / "app.db"))))
    repository.ensure_conversation("conv-1")
    services = AppServices(invoices=fake, actions=repository)
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set("conv-1")
    try:
        server = build_mcp_server()
        payload = json.dumps(
            {
                "contact_name": "Bob's Construction",
                "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
            }
        )
        async with Client(server) as client:
            await client.call_tool(
                "propose_action",
                {"action_type": "create_invoice", "payload_json": payload},
            )
    finally:
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)
    assert fake.write_calls == []
    assert fake.invoices == []


@pytest.mark.asyncio
async def test_propose_action_rejects_an_oversized_chat_amount(tmp_path) -> None:
    """Chat cannot store a pending action whose amount exceeds the backend limit."""
    fake = FakeInvoiceGateway()
    repository = ActionRepository(sessionmaker(bind=create_engine_for(str(tmp_path / "app.db"))))
    repository.ensure_conversation("conv-1")
    services = AppServices(invoices=fake, actions=repository)
    services_token = current_services.set(services)
    conversation_token = current_conversation_id.set("conv-1")
    try:
        server = build_mcp_server()
        payload = json.dumps(
            {
                "contact_name": "Bob's Construction",
                "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 1_000_000_000_000}],
            }
        )
        async with Client(server) as client:
            result = await client.call_tool(
                "propose_action",
                {"action_type": "create_invoice", "payload_json": payload},
            )
    finally:
        current_conversation_id.reset(conversation_token)
        current_services.reset(services_token)
    stored = repository.get_conversation("conv-1")
    assert stored is not None
    assert stored[1] == []
    assert "999999999999.99" in str(result)
    assert fake.write_calls == []
