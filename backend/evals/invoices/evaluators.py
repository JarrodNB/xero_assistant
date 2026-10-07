"""Purpose: Check that the invoices agent called the read tool the case names.

Public API:
- ExpectedRead
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.trace import trace_text


@dataclass
class ExpectedRead(Evaluator):
    """Check the invoices agent called one read tool and did not propose."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        """Match expect_tool against the tool trace."""
        expected = (ctx.metadata or {}).get("expect_tool")
        trace = trace_text(ctx.output)
        if "call propose_action" in trace or "call delegate_task" in trace:
            return False
        if not isinstance(expected, str) or not expected:
            return False
        return f"call {expected}" in trace
