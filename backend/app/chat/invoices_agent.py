"""Purpose: Build the invoices subagent that owns contact and invoice reads.

Public API:
- INVOICE_READ_TOOLS
- build_invoices_agent
"""

from fastmcp import FastMCP
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from app.chat.prompt import INVOICES_PROMPT
from app.chat.guardrails.redaction import protect_model_history

INVOICE_READ_TOOLS = frozenset(
    {
        "find_contacts",
        "find_invoices",
        "get_invoice",
        "summarize_invoices",
        "compare_invoice_totals",
    }
)


def build_invoices_agent(model: str | Model, server: FastMCP) -> Agent:
    """Create the read-only invoices agent, including contact lookup."""
    allowed = set(INVOICE_READ_TOOLS)
    return Agent(
        model,
        name="invoices",
        description=(
            "Looks up contacts and invoices in the demo company and returns names, amounts, and totals. "
            "Does not propose writes."
        ),
        instructions=INVOICES_PROMPT,
        capabilities=[ProcessHistory(protect_model_history)],
        toolsets=[MCPToolset(server).filtered(lambda _ctx, tool: tool.name in allowed)],
    )
