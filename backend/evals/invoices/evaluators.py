"""Purpose: Check that the invoices agent called the read tool the case names.

Public API:
- ExpectedRead
- FinancialAnswer
"""

from dataclasses import dataclass
import re

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.trace import trace_text, answer_text


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


@dataclass
class FinancialAnswer(Evaluator):
    """Mechanically check currency labels, empty results and incomplete-read wording."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        """Check only answer text so correct tool JSON cannot hide incorrect narration."""
        scenario = (ctx.metadata or {}).get("financial_scenario")
        answer = answer_text(ctx.output)
        if scenario is None:
            return True
        if scenario == "mixed":
            labelled = all(re.search(rf"(?:\b{currency}\b\s*[:$]?\s*100(?:\.00)?\b|\b100(?:\.00)?\s*{currency}\b)", answer)
                           for currency in ("AUD", "USD"))
            return labelled and not re.search(r"\b200(?:\.00)?\b", answer)
        if scenario == "empty":
            return bool(re.search(r"(?:no|zero|0)\s+(?:matching\s+|recognised\s+)?invoices", answer, re.I)) and not re.search(r"\b(?:AUD|USD)\b", answer)
        if scenario == "truncated":
            limitation = re.search(r"incomplete|partial|truncat|cannot determine|can't determine", answer, re.I)
            recovery = re.search(r"narrow|smaller|shorter|filter", answer, re.I)
            false_absence = re.search(r"\bno (?:matching )?invoices\b|\b(?:total|balance)\s+(?:is\s+)?(?:0|200)\b", answer, re.I)
            return bool(limitation and recovery and not false_absence)
        return False
