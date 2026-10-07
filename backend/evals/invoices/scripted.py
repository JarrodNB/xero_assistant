"""Purpose: Harness stand-in for the invoices agent. Golden pytest stays on the configured chat model.

Public API:
- scripted_invoices_model
"""

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

_CALLS = 0


def scripted_invoices_model() -> FunctionModel:
    """Return the harness stand-in that calls one read tool and then reports the rows."""
    return FunctionModel(scripted_respond)


def scripted_respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Call the read tool this task needs, then return names and amounts."""
    del info
    user = _latest_user_text(messages)
    called = _called_tools(messages)
    tool_name, args = _read_tool(user)
    if tool_name not in called:
        return _call(tool_name, args)
    return ModelResponse(parts=[TextPart(content=_report(user))])


def _read_tool(user: str) -> tuple[str, dict[str, object]]:
    """Pick the read tool for one invoices task."""
    folded = user.casefold()
    if "inv-" in folded:
        return ("get_invoice", {"invoice_number": "INV-1001"})
    if "february" in folded:
        return (
            "compare_invoice_totals",
            {
                "period_a_start": "2026-01-01",
                "period_a_end": "2026-01-31",
                "period_b_start": "2026-02-01",
                "period_b_end": "2026-02-28",
            },
        )
    if "overdue" in folded:
        return ("find_invoices", {"status": "AUTHORISED"})
    if "bob" in folded:
        return ("find_contacts", {"name": "Bob's Construction"})
    return ("summarize_invoices", {})


def _report(user: str) -> str:
    """Return the rows a scripted read would hand back."""
    folded = user.casefold()
    if "inv-" in folded:
        return "Invoice INV-1001 was not found."
    if "bob" in folded:
        return "No matching contact was found."
    if "february" in folded:
        return "January 2026 total 0. February 2026 total 0."
    if "overdue" in folded:
        return "No invoices are overdue."
    return "Unpaid total is 0."


def _call(tool_name: str, args: dict[str, object]) -> ModelResponse:
    """Build one tool call with a unique id."""
    global _CALLS
    _CALLS += 1
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=f"inv-{_CALLS}")])


def _called_tools(messages: list[ModelMessage]) -> list[str]:
    """List tool names already requested in this run."""
    names: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolCallPart):
                names.append(part.tool_name)
    return names


def _latest_user_text(messages: list[ModelMessage]) -> str:
    """Return the newest user prompt in the run."""
    text = ""
    for message in messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, UserPromptPart):
                content = part.content
                text = content if isinstance(content, str) else str(content)
    return text
