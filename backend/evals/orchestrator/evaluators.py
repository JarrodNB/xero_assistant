"""Purpose: Check that the orchestrator delegated or proposed as the case requires.

Public API:
- ExpectedDelegate
"""

from dataclasses import dataclass

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
        if expected not in {"invoices", "none"}:
            return False
        proposed = "call propose_action" in trace
        if metadata.get("expect_propose") is True and not proposed:
            return False
        if metadata.get("expect_propose") is False and proposed:
            return False
        return True
