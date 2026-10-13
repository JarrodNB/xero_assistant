"""Purpose: Check that the orchestrator delegated or proposed as the case requires.

Public API:
- ExpectedDelegate
- PendingProposalEvidence
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.trace import trace_text


@dataclass
class PendingProposalEvidence(Evaluator):
    """Require successful pending tool evidence when a case calls for a proposal."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        """Keep a semantic judge from approving an answer that never stored the requested proposal."""
        if (ctx.metadata or {}).get("expect_propose") is not True:
            return True
        trace = trace_text(ctx.output)
        calls = [line for line in trace.splitlines() if line.startswith("call propose_action ")]
        results = [line.removeprefix("result propose_action ") for line in trace.splitlines() if line.startswith("result propose_action ")]
        if len(calls) != 1 or len(results) != 1:
            return False
        try:
            result = json.loads(results[0])
            call = json.loads(calls[0].removeprefix("call propose_action "))
        except (ValueError, TypeError):
            return False
        return (
            isinstance(result, dict)
            and isinstance(call, dict)
            and result.get("ok") is True
            and result.get("kind") == "proposed_action"
            and result.get("status") == "pending"
            and result.get("action_type") == call.get("action_type")
            and call.get("action_type") in {"create_contact", "create_invoice", "update_invoice", "void_invoice"}
            and isinstance(result.get("payload"), dict)
        )


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
        if not PendingProposalEvidence().evaluate(ctx):
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
                amount = sum(Decimal(str(item["quantity"])) * Decimal(str(item["unit_amount"])) for item in payload["line_items"])
            except (ValueError, KeyError, TypeError, IndexError, InvalidOperation):
                return False
            if amount != Decimal(str(expected_amount)):
                return False
        if metadata.get("expect_propose") is False and proposed:
            return False
        return True
