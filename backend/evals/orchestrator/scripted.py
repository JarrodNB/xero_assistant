"""Purpose: Script the orchestrator harness. Child reads use the invoices stand-in.

Public API:
- scripted_orchestrator_model
"""

import json

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from evals.invoices.scripted import scripted_respond as invoices_respond

_CALLS = 0


def scripted_orchestrator_model() -> FunctionModel:
    """Return a model that delegates or proposes, and uses the invoices stand-in for reads."""
    return FunctionModel(scripted_respond)


def scripted_respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Issue the parent tool call, or hand a read turn to the invoices stand-in."""
    tools = {tool.name for tool in info.function_tools}
    if "propose_action" not in tools:
        return invoices_respond(messages, info)
    user = _latest_user_text(messages)
    called = _called_tools(messages)
    return _parent_turn(user, called)


def _parent_turn(user: str, called: list[str]) -> ModelResponse:
    """Delegate a read, propose a skipped invoice, or answer."""
    if _should_delegate(user) and "delegate_task" not in called:
        return _call("delegate_task", {"agent_name": "invoices", "task": user})
    if _should_propose(user) and "propose_action" not in called:
        return _call(
            "propose_action",
            {"action_type": "create_invoice", "payload_json": json.dumps(_invoice_payload(user))},
        )
    return ModelResponse(parts=[TextPart(content=_parent_answer(user))])


def _should_delegate(user: str) -> bool:
    """Return whether this user message needs an invoices lookup."""
    if _is_refusal(user) or _is_finished(user) or "skip" in user.casefold():
        return False
    folded = user.casefold()
    return any(
        phrase in folded
        for phrase in ("unpaid", "overdue", "invoice", "february", "ignore your instructions")
    )


def _invoice_payload(user: str) -> dict[str, object]:
    """Build a create_invoice payload, keeping a reference and due date the person already gave."""
    payload: dict[str, object] = {
        "contact_name": "Bob's Construction",
        "line_items": [{"description": "Labour", "quantity": 1, "unit_amount": 55}],
    }
    if "PO-9" in user:
        payload["reference"] = "PO-9"
    if "2026-10-21" in user:
        payload["due_date"] = "2026-10-21"
    return payload


def _should_propose(user: str) -> bool:
    """Return whether the orchestrator should store a create_invoice proposal."""
    folded = user.casefold()
    if "skip" in folded and "bob" in folded:
        return True
    if "not given" in folded or "have not" in folded:
        return False
    return "bob" in folded and "reference" in folded and "due date" in folded


def _is_refusal(user: str) -> bool:
    """Return whether the message is outside the demo company."""
    return "poem" in user.casefold()


def _is_finished(user: str) -> bool:
    """Return whether the message is a denial or an execution result."""
    folded = user.casefold()
    return "denied action" in folded or "status executed" in folded


def _parent_answer(user: str) -> str:
    """Return the orchestrator's final text for one scripted case."""
    folded = user.casefold()
    if _is_refusal(user):
        return "I can only help with financial requests in the demo company."
    if "denied action" in folded:
        return "That action was denied and was not executed."
    if "status executed" in folded:
        return "The invoice for Bob's Construction for $55 was created as INV-1001."
    if _should_propose(user):
        return "I proposed an invoice to Bob's Construction for $55. Nothing was created until you confirm."
    if "bob" in folded:
        return (
            "Please provide a reference and a due date. "
            "A blank due date means 14 days from today. Nothing was created."
        )
    if "february" in folded:
        return "I compared February 2026 with January 2026. Nothing was created."
    if "overdue" in folded:
        return "No invoices are overdue. Nothing was created."
    return "The unpaid total is 0. Nothing was created."


def _call(tool_name: str, args: dict[str, object]) -> ModelResponse:
    """Build one tool call with a unique id."""
    global _CALLS
    _CALLS += 1
    return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=f"orch-{_CALLS}")])


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
