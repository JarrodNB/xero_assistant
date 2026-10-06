"""Purpose: Build the PydanticAI agent that uses the in-process MCP tools.

Public API:
- build_chat_agent
"""

from fastmcp import FastMCP
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models import Model

from app.chat.guardrails import chat_guardrails
from app.chat.prompt import SYSTEM_PROMPT


def build_chat_agent(model: str | Model, server: FastMCP) -> Agent:
    """Create an agent whose tools come from the in-process MCP server."""
    return Agent(
        model,
        instructions=SYSTEM_PROMPT,
        toolsets=[MCPToolset(server)],
        capabilities=chat_guardrails(),
    )
