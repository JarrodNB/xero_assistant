"""Purpose: Split an eval answer from the tool trace appended after it.

Public API:
- TRACE_HEADING
- answer_text
- format_tool_trace
- trace_text
"""

import json

from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from app.chat.guardrails.pii import PiiVault
from app.chat.guardrails.redaction import redact_for_trace

TRACE_HEADING = "\nTool trace:\n"


def answer_text(output: object) -> str:
    """Return the assistant answer, without the appended tool trace."""
    text = str(output)
    if TRACE_HEADING in text:
        return text.split(TRACE_HEADING, 1)[0].strip()
    return text


def trace_text(output: object) -> str:
    """Return the tool trace appended to an eval answer."""
    text = str(output)
    if TRACE_HEADING not in text:
        return ""
    return text.split(TRACE_HEADING, 1)[1]


def format_tool_trace(result: object) -> str:
    """Format tool calls and returns without leaving personal data in the eval output."""
    vault = PiiVault()
    lines: list[str] = []
    for message in result.all_messages():  # type: ignore[attr-defined]
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                lines.append(f"call {part.tool_name} {_trace_text(vault, _args_text(part.args))}")
            elif isinstance(part, ToolReturnPart):
                lines.append(f"result {part.tool_name} {_trace_text(vault, str(part.content))}")
    return "\n".join(lines)


def _args_text(args: object) -> str:
    """Serialize tool arguments for the eval trace."""
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False, default=str)
    except TypeError:
        return str(args)


def _trace_text(vault: PiiVault, value: str) -> str:
    """Protect one tool call or result with a vault that lives only for this trace."""
    return redact_for_trace(value, vault)
