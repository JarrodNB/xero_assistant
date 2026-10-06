"""Purpose: Check the golden dataset and its deterministic evaluators.

Public API:
- test_golden_dataset_has_an_llm_judge_per_case
- test_unconfirmed_write_claim_evaluator
- test_deterministic_golden_evaluators_stay_offline
- test_live_llm_judge
"""

import os
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_evals.evaluators import EvaluatorContext, GEval, LLMJudge
from pydantic_evals.otel.span_tree import SpanTree

from evals.evaluators import DoesNotClaimUnconfirmedWrite
from evals.run_invoice_evals import live_judge_enabled, load_invoice_golden_dataset, evaluate_invoice_dataset


def test_golden_dataset_has_an_llm_judge_per_case() -> None:
    """Every golden case names what a good answer must say."""
    dataset = load_invoice_golden_dataset()
    assert dataset.name == "invoice_golden"
    assert dataset.cases
    for case in dataset.cases:
        assert any(isinstance(evaluator, LLMJudge) for evaluator in case.evaluators or [])
    assert any(isinstance(evaluator, GEval) for evaluator in dataset.evaluators)


def test_unconfirmed_write_claim_evaluator() -> None:
    """A write claim fails unless the case already contains an execution result."""
    evaluator = DoesNotClaimUnconfirmedWrite()
    claimed = _context("The invoice was created.", {"execution_result": False})
    allowed = _context("The invoice was created.", {"execution_result": True})
    quiet = _context("I checked the records. Nothing was created.", {"execution_result": False})
    assert evaluator.evaluate(claimed) is False
    assert evaluator.evaluate(allowed) is True
    assert evaluator.evaluate(quiet) is True


@pytest.mark.asyncio
async def test_deterministic_golden_evaluators_stay_offline(tmp_path: Path) -> None:
    """The shared evaluators run against a scripted model and do not call a provider."""
    def respond(_messages, _info):  # type: ignore[no-untyped-def]
        """Return a safe answer that does not claim a write."""
        return ModelResponse(parts=[TextPart(content="I checked the invoice records. Nothing was created.")])

    report = await evaluate_invoice_dataset(FunctionModel(respond), tmp_path, include_llm_judge=False)
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


@pytest.mark.asyncio
async def test_live_llm_judge(tmp_path: Path) -> None:
    """Score the golden dataset with LLMJudge when a real OpenAI key is configured."""
    if not live_judge_enabled():
        pytest.skip("OPENAI_API_KEY is not set to a live key")
    report = await evaluate_invoice_dataset(os.environ["MODEL"], tmp_path, include_llm_judge=True)
    assert report.failures == []


def _context(output: str, metadata: dict) -> EvaluatorContext:
    """Build the evaluator context for one direct assertion."""
    return EvaluatorContext(
        name="direct",
        inputs="question",
        metadata=metadata,
        expected_output=None,
        output=output,
        duration=0.0,
        _span_tree=SpanTree(),
        attributes={},
        metrics={},
    )
