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
from app.chat.execution import budget_capabilities
from app.config import Settings

INVOICE_READ_TOOLS = frozenset(
    {
        "find_contacts",
        "find_invoices",
        "get_invoice",
        "summarize_invoices",
        "compare_invoice_totals",
    }
)


def build_invoices_agent(model: str | Model, server: FastMCP, settings: Settings | None = None) -> Agent:
    """Create the read-only invoices agent, including contact lookup."""
    allowed = set(INVOICE_READ_TOOLS)
    return Agent(
        model,
        name="invoices",
        retries=settings.ai_validation_retries if settings else 1,
        description=(
            "Looks up contacts and invoices in the demo company and returns names, amounts, and totals. "
            "Does not propose writes."
        ),
        instructions=INVOICES_PROMPT,
        capabilities=[*budget_capabilities(), ProcessHistory(protect_model_history)],
        toolsets=[MCPToolset(server).filtered(lambda _ctx, tool: tool.name in allowed)],
    )
