"""Purpose: Build a read-only typed fact-selector whose output cannot contain financial prose.

Public API:
- build_report_agent
"""

import json

from fastmcp import FastMCP
from pydantic_ai import Agent, ModelRetry, UsageLimitExceeded
from pydantic_ai.capabilities import Hooks
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.mcp import MCPToolset

from app.chat.execution import budget_capabilities
from app.chat.guardrails import chat_guardrails
from app.chat.report_facts import ReportFactSelection, current_report_facts
from app.chat.report_prompt import REPORT_PROMPT
from app.config import Settings


def build_report_agent(model, server: FastMCP, settings: Settings) -> Agent:
    """Offer report reads only and validate every selected evidence key before rendering."""
    async def bound_input(ctx, request_context):
        """Cap actual accumulated messages and tool schemas before each provider request."""
        parameters = request_context.model_request_parameters
        tools = list(parameters.function_tools) + list(parameters.output_tools)
        schemas = [{"name": tool.name, "description": tool.description, "schema": tool.parameters_json_schema} for tool in tools]
        size = len(ModelMessagesTypeAdapter.dump_json(request_context.messages).decode()) + len(json.dumps(schemas)) + len(REPORT_PROMPT)
        if size > settings.report_model_character_limit:
            raise UsageLimitExceeded("Protected report input character budget exhausted")
        return request_context

    agent = Agent(model, name="report_explanation", output_type=ReportFactSelection,
                  retries=settings.ai_validation_retries, instructions=REPORT_PROMPT,
                  toolsets=[MCPToolset(server).filtered(lambda _ctx, tool: tool.name in {"compare_profit_and_loss", "compare_balance_sheets"})],
                  capabilities=[*budget_capabilities(), Hooks(before_model_request=bound_input), *chat_guardrails()])

    @agent.output_validator
    def validate_selection(result: ReportFactSelection) -> ReportFactSelection:
        """Unknown source references are validation failures, never printable model content."""
        facts = current_report_facts.get()
        if facts is None or any(key not in facts.offered_keys() for key in result.evidence):
            raise ModelRetry("Choose only supplied evidence keys.")
        if result.focus == "selected" and facts.selected_key is None:
            raise ModelRetry("No account is selected; choose overview.")
        if result.focus == "largest_expense" and facts.report.report_type != "profit_and_loss":
            raise ModelRetry("Position reports have no expense focus; choose overview.")
        return result

    return agent
