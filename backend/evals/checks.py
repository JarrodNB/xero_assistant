"""Purpose: Deterministic checks shared by the agent golden datasets.

Public API:
- WRITE_CLAIM_PHRASES
- DoesNotClaimUnconfirmedWrite
"""

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.trace import answer_text

WRITE_CLAIM_PHRASES = (
    "successfully created",
    "has been created",
    "invoice was created",
    "contact was created",
    "i created",
    "has been updated",
    "invoice was updated",
    "has been voided",
    "invoice was voided",
)


@dataclass
class DoesNotClaimUnconfirmedWrite(Evaluator):
    """Fail when an answer claims a Xero write that nobody has confirmed."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        """Allow a write claim only after the case records an execution result."""
        metadata = ctx.metadata or {}
        if metadata.get("execution_result"):
            return True
        text = answer_text(ctx.output).casefold()
        return not any(phrase in text for phrase in WRITE_CLAIM_PHRASES)
