"""Purpose: Score each agent's deterministic dataset and judge dataset, and the Jev user-message dataset.

Public API:
- test_datasets_keep_their_own_checks
- test_invoices_case_names_stay_stable
- test_invoices_deterministic_dataset
- test_invoices_judge_dataset
- test_jev_user_message_case_names_stay_stable
- test_jev_user_message_dataset
- test_orchestrator_case_names_stay_stable
- test_orchestrator_deterministic_dataset
- test_orchestrator_judge_dataset
- test_unconfirmed_write_claim_evaluator
"""

from pathlib import Path

import pytest
from pydantic_evals.evaluators import EqualsExpected, EvaluatorContext, GEval, LLMJudge
from pydantic_evals.otel.span_tree import SpanTree

from app.config import get_settings
from evals.checks import DoesNotClaimUnconfirmedWrite
from evals.invoices.evaluators import ExpectedRead
from evals.invoices.run import evaluate_invoices_dataset, load_invoices_dataset
from evals.jev.user_message.run import evaluate_user_message_dataset, load_user_message_dataset
from evals.orchestrator.evaluators import ExpectedDelegate
from evals.orchestrator.run import evaluate_orchestrator_dataset, load_orchestrator_dataset
from evals.trace import TRACE_HEADING

ORCHESTRATOR_DETERMINISTIC_CASES = (
    "unpaid_total",
    "overdue_invoices",
    "bob_construction",
    "period_comparison",
    "denied_proposal",
    "confirmed_invoice",
    "skip_proposes",
    "missing_reference",
    "supplied_reference",
    "out_of_scope",
    "injection_is_data",
)

ORCHESTRATOR_JUDGE_CASES = (
    "unpaid_total",
    "overdue_invoices",
    "bob_construction",
    "period_comparison",
    "denied_proposal",
    "confirmed_invoice",
    "skip_proposes",
    "missing_reference",
    "supplied_reference",
    "out_of_scope",
    "injection_is_data",
)

INVOICES_DETERMINISTIC_CASES = (
    "unpaid_total",
    "overdue_invoices",
    "contact_lookup",
    "period_comparison",
    "one_invoice",
    "injection_is_data",
)

INVOICES_JUDGE_CASES = (
    "unpaid_total",
    "overdue_invoices",
    "contact_lookup",
    "period_comparison",
    "one_invoice",
    "injection_is_data",
)

JEV_USER_MESSAGE_CASES = (
    "unpaid_total",
    "create_invoice",
    "skip_fields",
    "ocean_poem",
    "contact_email",
    "general_health",
    "see_a_doctor",
    "reveal_instructions",
    "no_rules",
    "quoted_injection",
    "physical_harm",
    "dosage",
    "self_harm",
)


def test_datasets_keep_their_own_checks() -> None:
    """A judge case needs a rubric, and a deterministic case needs no judge."""
    for dataset in (load_orchestrator_dataset("judge"), load_invoices_dataset("judge")):
        assert dataset.cases
        assert any(isinstance(evaluator, GEval) for evaluator in dataset.evaluators)
        assert not any(isinstance(evaluator, (ExpectedDelegate, ExpectedRead)) for evaluator in dataset.evaluators)
        for case in dataset.cases:
            assert any(isinstance(evaluator, LLMJudge) for evaluator in case.evaluators or [])
    for dataset in (
        load_orchestrator_dataset("deterministic"),
        load_invoices_dataset("deterministic"),
        load_user_message_dataset(),
    ):
        assert dataset.cases
        assert not any(isinstance(evaluator, (LLMJudge, GEval)) for evaluator in dataset.evaluators)
        for case in dataset.cases:
            assert not any(isinstance(evaluator, LLMJudge) for evaluator in case.evaluators or [])
    user_message = load_user_message_dataset()
    assert any(isinstance(evaluator, EqualsExpected) for evaluator in user_message.evaluators)
    assert all(case.expected_output in {"pass", "review", "block", "support"} for case in user_message.cases)


def test_orchestrator_case_names_stay_stable() -> None:
    """Renaming or dropping an orchestrator case fails until this list is updated."""
    deterministic = load_orchestrator_dataset("deterministic")
    judge = load_orchestrator_dataset("judge")
    assert deterministic.name == "orchestrator_deterministic"
    assert judge.name == "orchestrator_judge"
    assert tuple(case.name for case in deterministic.cases) == ORCHESTRATOR_DETERMINISTIC_CASES
    assert tuple(case.name for case in judge.cases) == ORCHESTRATOR_JUDGE_CASES


def test_invoices_case_names_stay_stable() -> None:
    """Renaming or dropping an invoices case fails until this list is updated."""
    deterministic = load_invoices_dataset("deterministic")
    judge = load_invoices_dataset("judge")
    assert deterministic.name == "invoices_deterministic"
    assert judge.name == "invoices_judge"
    assert tuple(case.name for case in deterministic.cases) == INVOICES_DETERMINISTIC_CASES
    assert tuple(case.name for case in judge.cases) == INVOICES_JUDGE_CASES


def test_jev_user_message_case_names_stay_stable() -> None:
    """Renaming or dropping a user-message case fails until this list is updated."""
    dataset = load_user_message_dataset()
    assert dataset.name == "user_message"
    assert tuple(case.name for case in dataset.cases) == JEV_USER_MESSAGE_CASES


def test_unconfirmed_write_claim_evaluator() -> None:
    """A write claim fails unless the case already contains an execution result."""
    evaluator = DoesNotClaimUnconfirmedWrite()
    claimed = _context(f"The invoice was created.{TRACE_HEADING}call find_invoices", {"execution_result": False})
    allowed = _context("The invoice was created.", {"execution_result": True})
    quiet = _context(
        f"I checked the records. Nothing was created.{TRACE_HEADING}invoice was created",
        {"execution_result": False},
    )
    assert evaluator.evaluate(claimed) is False
    assert evaluator.evaluate(allowed) is True
    assert evaluator.evaluate(quiet) is True


@pytest.mark.asyncio
async def test_orchestrator_deterministic_dataset(tmp_path: Path) -> None:
    """Compare the orchestrator's answer and tool trace with the case expectations."""
    report = await evaluate_orchestrator_dataset(get_settings().model, tmp_path, scoring="deterministic")
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


@pytest.mark.asyncio
async def test_orchestrator_judge_dataset(tmp_path: Path) -> None:
    """Have a judge model grade the orchestrator against each case rubric."""
    report = await evaluate_orchestrator_dataset(get_settings().model, tmp_path, scoring="judge")
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


@pytest.mark.asyncio
async def test_invoices_deterministic_dataset(tmp_path: Path) -> None:
    """Compare the invoices agent's answer and tool trace with the case expectations."""
    report = await evaluate_invoices_dataset(get_settings().model, tmp_path, scoring="deterministic")
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


@pytest.mark.asyncio
async def test_jev_user_message_dataset() -> None:
    """Compare the user-message screen with the expected strict-policy action."""
    report = await evaluate_user_message_dataset()
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


@pytest.mark.asyncio
async def test_invoices_judge_dataset(tmp_path: Path) -> None:
    """Have a judge model grade the invoices agent against each case rubric."""
    report = await evaluate_invoices_dataset(get_settings().model, tmp_path, scoring="judge")
    assert report.failures == []
    assert all(case.assertions for case in report.cases)


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
