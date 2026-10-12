"""Purpose: Score each agent's deterministic dataset and judge dataset, and the Jev user-message dataset.

Public API:
- test_datasets_keep_their_own_checks
- test_invoices_case_names_stay_stable
- test_invoices_deterministic_dataset
- test_invoices_judge_dataset
- test_jev_user_message_case_names_stay_stable
- test_jev_user_message_eval_protects_prompt_and_history
- test_jev_user_message_dataset
- test_orchestrator_case_names_stay_stable
- test_orchestrator_deterministic_dataset
- test_orchestrator_judge_dataset
- test_unconfirmed_write_claim_evaluator
- test_tool_trace_excludes_historical_calls
- test_tool_trace_keeps_redacted_payload_parseable
- test_pending_proposal_evidence_requires_successful_matching_result
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_evals.evaluators import EqualsExpected, EvaluatorContext, GEval, LLMJudge
from pydantic_evals.otel.span_tree import SpanTree
from pydantic_ai.messages import ModelResponse, ToolCallPart

from app.chat.guardrails.context import current_guardrail_context
from app.chat.guardrails.pii import current_vault
from app.config import get_settings
from evals.checks import DoesNotClaimUnconfirmedWrite
from evals.reporting import assert_report_integrity
from evals.invoices.evaluators import ExpectedRead
from evals.invoices.run import evaluate_invoices_dataset, load_invoices_dataset
from evals.jev.user_message.run import (
    EvaluationMessage,
    UserMessageInput,
    evaluate_user_message_dataset,
    load_user_message_dataset,
    screen_user_message_input,
)
from evals.orchestrator.evaluators import ExpectedDelegate, PendingProposalEvidence
from evals.orchestrator.run import evaluate_orchestrator_dataset, load_orchestrator_dataset
from evals.trace import TRACE_HEADING, format_tool_trace

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
    "oversized_chat_amount",
    "same_contact_follow_up",
    "reference_only",
    "due_date_only",
    "missing_required_amount",
    "contact_without_email",
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
    "oversized_chat_amount",
    "same_contact_follow_up",
    "reference_only",
    "due_date_only",
    "missing_required_amount",
    "contact_without_email",
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
    "invoice_maximum_follow_up",
    "hazardous_history_safe_follow_up",
    "hazardous_history_adopted",
)


class _RecordingJev:
    """Allow one evaluation input while recording its provider-facing state."""

    def __init__(self) -> None:
        """Start without provider-facing text."""
        self.text = ""

    async def guard(self, text: str, side: str) -> str:
        """Record the input-side text and allow it."""
        assert side == "input"
        self.text = text
        return "pass"


def test_datasets_keep_their_own_checks() -> None:
    """A judge case needs a rubric, and a deterministic case needs no judge."""
    for dataset in (load_orchestrator_dataset("judge"), load_invoices_dataset("judge")):
        assert dataset.cases
        assert any(isinstance(evaluator, GEval) for evaluator in dataset.evaluators)
        assert not any(isinstance(evaluator, (ExpectedDelegate, ExpectedRead)) for evaluator in dataset.evaluators)
        assert any(isinstance(evaluator, DoesNotClaimUnconfirmedWrite) for evaluator in dataset.evaluators)
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


@pytest.mark.asyncio
async def test_jev_user_message_eval_protects_prompt_and_history() -> None:
    """The eval sends only protected prompt and history text to its Jev provider."""
    screener = _RecordingJev()
    case = UserMessageInput(
        prompt="Use current@example.com with sk-abcdefghijklmnopqrstuvwxyz123456.",
        previous_messages=[
            EvaluationMessage(role="assistant", content="Earlier contact was prior@example.com.")
        ],
    )
    result = await screen_user_message_input(screener, case)
    assert result == "pass"
    assert "current@example.com" not in screener.text
    assert "prior@example.com" not in screener.text
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in screener.text
    assert "[redacted_email:" in screener.text
    assert current_vault.get() is None
    assert current_guardrail_context.get() is None


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
    assert evaluator.evaluate(_context("Nothing has been created yet.", {})) is True
    assert evaluator.evaluate(_context("No invoice has been created.", {})) is True
    assert evaluator.evaluate(_context("Nothing has been created yet. I created another invoice.", {})) is False


def test_tool_trace_excludes_historical_calls() -> None:
    """Only calls from the evaluated turn count toward proposal and delegation scores."""
    old = ModelResponse(parts=[ToolCallPart(tool_name="propose_action", args={})])
    new = ModelResponse(parts=[ToolCallPart(tool_name="delegate_task", args={"agent_name": "invoices"})])
    result = SimpleNamespace(all_messages=lambda: [old, new], new_messages=lambda: [new])
    trace = format_tool_trace(result)
    assert "call delegate_task" in trace
    assert "call propose_action" not in trace


def test_tool_trace_keeps_redacted_payload_parseable() -> None:
    """Nested proposal JSON retains its schema while sensitive values are masked."""
    payload = {"name": "Cedar Demo Supplies", "email": "prior@example.com", "reference": "sk-abcdefghijklmnopqrstuvwxyz123456"}
    message = ModelResponse(parts=[ToolCallPart(tool_name="propose_action", args={
        "action_type": "create_contact", "payload_json": json.dumps(payload),
    })])
    trace = format_tool_trace(SimpleNamespace(new_messages=lambda: [message]))
    args = json.loads(trace.removeprefix("call propose_action "))
    restored_payload = json.loads(args["payload_json"])
    assert set(restored_payload) == set(payload)
    assert "prior@example.com" not in trace
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in trace
    assert "[redacted_email:" in restored_payload["email"]


def test_pending_proposal_evidence_requires_successful_matching_result() -> None:
    """Freeform pending claims, errors, and mismatched action types cannot pass the integrity gate."""
    evaluator = PendingProposalEvidence()
    call = 'call propose_action {"action_type": "create_contact", "payload_json": "{}"}\n'
    result = {"ok": True, "kind": "proposed_action", "status": "pending", "action_id": "synthetic-action", "action_type": "create_contact", "payload": {"name": "Cedar Demo Supplies"}}
    output = f"Please confirm.{TRACE_HEADING}{call}result propose_action {json.dumps(result)}"
    assert evaluator.evaluate(_context(output, {"expect_propose": True})) is True
    for rejected in ("pending", {**result, "ok": False}, {**result, "action_type": "create_invoice"}, {**result, "action_id": ""}):
        output = f"Please confirm.{TRACE_HEADING}{call}result propose_action {json.dumps(rejected)}"
        assert evaluator.evaluate(_context(output, {"expect_propose": True})) is False
    assert evaluator.evaluate(_context(f"Pending.{TRACE_HEADING}{call}", {"expect_propose": True})) is False
    invalid_call = f"Pending.{TRACE_HEADING}call propose_action []\nresult propose_action {json.dumps(result)}"
    assert evaluator.evaluate(_context(invalid_call, {"expect_propose": True})) is False


@pytest.mark.live_eval
@pytest.mark.asyncio
async def test_orchestrator_deterministic_dataset(tmp_path: Path) -> None:
    """Compare the orchestrator's answer and tool trace with the case expectations."""
    report = await evaluate_orchestrator_dataset(get_settings().model, tmp_path, scoring="deterministic", live=True)
    assert_report_integrity(report, [case.name for case in load_orchestrator_dataset("deterministic").cases])


@pytest.mark.live_eval
@pytest.mark.asyncio
async def test_orchestrator_judge_dataset(tmp_path: Path) -> None:
    """Have a judge model grade the orchestrator against each case rubric."""
    report = await evaluate_orchestrator_dataset(get_settings().model, tmp_path, scoring="judge", live=True)
    assert_report_integrity(report, [case.name for case in load_orchestrator_dataset("judge").cases])


@pytest.mark.live_eval
@pytest.mark.asyncio
async def test_invoices_deterministic_dataset(tmp_path: Path) -> None:
    """Compare the invoices agent's answer and tool trace with the case expectations."""
    report = await evaluate_invoices_dataset(get_settings().model, tmp_path, scoring="deterministic", live=True)
    assert_report_integrity(report, [case.name for case in load_invoices_dataset("deterministic").cases])


@pytest.mark.live_eval
@pytest.mark.asyncio
async def test_jev_user_message_dataset() -> None:
    """Compare the user-message screen with the expected strict-policy action."""
    report = await evaluate_user_message_dataset(live=True)
    assert_report_integrity(report, [case.name for case in load_user_message_dataset().cases])


@pytest.mark.live_eval
@pytest.mark.asyncio
async def test_invoices_judge_dataset(tmp_path: Path) -> None:
    """Have a judge model grade the invoices agent against each case rubric."""
    report = await evaluate_invoices_dataset(get_settings().model, tmp_path, scoring="judge", live=True)
    assert_report_integrity(report, [case.name for case in load_invoices_dataset("judge").cases])


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
