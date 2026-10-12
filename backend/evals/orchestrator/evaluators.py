"""Purpose: Check that the orchestrator delegated or proposed as the case requires.

Public API:
- ExpectedDelegate
"""

from dataclasses import dataclass
import json

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.trace import trace_text


@dataclass
class ExpectedDelegate(Evaluator):
    """Check the orchestrator delegated to invoices, or did not delegate."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        """Match expect_delegate and expect_propose against the tool trace."""
        metadata = ctx.metadata or {}
        expected = metadata.get("expect_delegate")
        trace = trace_text(ctx.output)
        delegated = "call delegate_task" in trace and "invoices" in trace
        if expected == "invoices" and not delegated:
            return False
        if expected == "none" and "call delegate_task" in trace:
            return False
        if expected not in {"invoices", "none", "optional"}:
            return False
        proposed = "call propose_action" in trace
        if metadata.get("expect_propose") is True and not proposed:
            return False
        if metadata.get("expect_propose") is True and ("result propose_action" not in trace or "pending" not in trace):
            return False
        expected_payload = metadata.get("expected_payload", {})
        if expected_payload:
            calls = [line.removeprefix("call propose_action ") for line in trace.splitlines() if line.startswith("call propose_action ")]
            if len(calls) != 1:
                return False
            try:
                payload = json.loads(json.loads(calls[0])["payload_json"])
            except (ValueError, KeyError, TypeError):
                return False
            if any(payload.get(key) != value for key, value in expected_payload.items()):
                return False
        expected_amount = metadata.get("expected_amount")
        if expected_amount is not None:
            calls = [line.removeprefix("call propose_action ") for line in trace.splitlines() if line.startswith("call propose_action ")]
            try:
                payload = json.loads(json.loads(calls[0])["payload_json"])
                amount = sum(item["quantity"] * item["unit_amount"] for item in payload["line_items"])
            except (ValueError, KeyError, TypeError, IndexError):
                return False
            if amount != expected_amount:
                return False
        if metadata.get("expect_propose") is False and proposed:
            return False
        return True
