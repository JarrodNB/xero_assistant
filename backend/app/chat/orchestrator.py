"""Purpose: Build the orchestrator that delegates reads and proposes writes.

Public API:
- build_chat_agent
"""

from fastmcp import FastMCP
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model
from pydantic_ai_harness import SubAgent, SubAgents

from app.chat.guardrails import chat_guardrails
from app.chat.guardrails.redaction import protect_model_history, tool_result_guardrail
from app.chat.invoices_agent import build_invoices_agent
from app.chat.prompt import SYSTEM_PROMPT, current_date_instruction
from app.chat.summary import apply_history_summary


def build_chat_agent(model: str | Model, server: FastMCP) -> Agent:
    """Create the orchestrator. It delegates reads and calls propose_action itself."""
    invoices = build_invoices_agent(model, server)
    propose = MCPToolset(server).filtered(lambda _ctx, tool: tool.name == "propose_action")
    return Agent(
        model,
        name="orchestrator",
        instructions=[SYSTEM_PROMPT, current_date_instruction],
        toolsets=[propose],
        capabilities=[
            *chat_guardrails(),
            ProcessHistory(apply_history_summary),
            ProcessHistory(protect_model_history),
            SubAgents(
                agents=[SubAgent(invoices, max_calls=3)],
                shared_capabilities=[tool_result_guardrail()],
                max_depth=2,
                contain_errors=True,
            ),
        ],
    )
