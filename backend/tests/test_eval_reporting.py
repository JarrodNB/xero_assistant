"""Purpose: Exercise report integrity, opt-in, and artifact privacy without providers.

Public API:
- test_report_integrity_rejects_invalid_reports
- test_library_distinguishes_assertions_and_execution_failures
- test_runner_artifacts_exclude_case_text
- test_paid_runners_require_opt_in
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EqualsExpected

from evals import reporting
from evals.invoices.run import evaluate_invoices_dataset
from evals.orchestrator.run import evaluate_orchestrator_dataset
from evals.jev.user_message.run import evaluate_user_message_dataset


def _case(name: str = "one", value: bool = True, *, errors: bool = False):
    """Build a small synthetic successful or failed report case."""
    return SimpleNamespace(name=name, assertions={"check": SimpleNamespace(value=value)},
        evaluator_failures=[object()] if errors else [])


@pytest.mark.parametrize("cases,failures,expected,message", [
    ([_case(value=False)], [], ["one"], "assertion failed"),
    ([], [], ["one"], "empty, incomplete"),
    ([_case()], [], ["one", "two"], "empty, incomplete"),
    ([_case(), _case()], [], ["one"], "duplicated"),
    ([_case("other")], [], ["one"], "unexpected"),
    ([_case(errors=True)], [], ["one"], "Evaluator execution failed"),
    ([], [object()], ["one"], "task execution failed"),
    ([_case()], [], [], "unique named cases"),
    ([_case()], [], ["one", "one"], "unique named cases"),
    ([SimpleNamespace(name="one", assertions={}, evaluator_failures=[])], [], ["one"], "No evaluator assertions"),
])
def test_report_integrity_rejects_invalid_reports(cases, failures, expected, message) -> None:
    """No empty, partial, false, or exception-containing report can pass."""
    with pytest.raises(AssertionError, match=message):
        reporting.assert_report_integrity(SimpleNamespace(cases=cases, failures=failures), expected)


def test_report_integrity_checks_report_evaluator_errors() -> None:
    """Report-level evaluator bugs cannot hide behind successful case assertions."""
    report = SimpleNamespace(cases=[_case()], failures=[], report_evaluator_failures=[])
    reporting.assert_report_integrity(report, ["one"])
    report.report_evaluator_failures = [object()]
    with pytest.raises(AssertionError, match="Report evaluator execution failed"):
        reporting.assert_report_integrity(report, ["one"])


class _BrokenEvaluator(Evaluator):
    """Raise rather than return a failed evaluator assertion."""

    def evaluate(self, ctx):
        """Simulate an evaluator bug without sending anything externally."""
        raise RuntimeError("synthetic private exception")


@pytest.mark.asyncio
async def test_library_distinguishes_assertions_and_execution_failures() -> None:
    """Check the installed library's actual failure locations with offline datasets."""
    async def answer(value):
        """Return the synthetic input unchanged."""
        return value

    async def broken(value):
        """Simulate a failed task."""
        raise RuntimeError("synthetic task exception")

    dataset = Dataset(name="failure-semantics", cases=[Case(name="one", inputs="wrong", expected_output="right")], evaluators=[EqualsExpected()])
    false_report = await dataset.evaluate(answer)
    assert not false_report.failures
    assert not false_report.cases[0].evaluator_failures
    assert next(iter(false_report.cases[0].assertions.values())).value is False
    with pytest.raises(AssertionError, match="assertion failed"):
        reporting.assert_report_integrity(false_report, ["one"])
    dataset.evaluators = [EqualsExpected(), _BrokenEvaluator()]
    report = await dataset.evaluate(answer)
    assert not report.failures
    assert report.cases[0].evaluator_failures
    with pytest.raises(AssertionError, match="Evaluator execution failed"):
        reporting.assert_report_integrity(report, ["one"])
    report = await dataset.evaluate(broken)
    assert report.failures
    with pytest.raises(AssertionError, match="task execution failed"):
        reporting.assert_report_integrity(report, ["one"])


@pytest.mark.asyncio
@pytest.mark.parametrize("passed", [True, False])
async def test_runner_artifacts_exclude_case_text(tmp_path: Path, monkeypatch, passed: bool) -> None:
    """Retain useful success/failure evidence without inputs, outputs, or exception text."""
    from pydantic_evals import increment_eval_metric, set_eval_attribute

    async def answer(value):
        """Return synthetic sensitive content and task usage to test the allowlist."""
        increment_eval_metric("input_tokens", 12)
        increment_eval_metric("private_metric", 999)
        set_eval_attribute("private_attribute", value)
        return value

    secret = "private@example.com sk-synthetic-secret"
    dataset = Dataset(name="synthetic", cases=[Case(name="one", inputs=secret,
        expected_output=secret if passed else "different")], evaluators=[EqualsExpected()])
    source = tmp_path / "dataset.yaml"
    source.write_text("synthetic dataset", encoding="utf-8")
    monkeypatch.setattr(reporting, "ARTIFACT_DIRECTORY", tmp_path / "artifacts")
    if passed:
        await reporting.evaluate_dataset(dataset, answer, live=True, dataset_path=source, model="test-snapshot", prompt_paths=[source])
    else:
        with pytest.raises(AssertionError, match="assertion failed"):
            await reporting.evaluate_dataset(dataset, answer, live=True, dataset_path=source, model="test-snapshot", prompt_paths=[source])
    raw = next((tmp_path / "artifacts").glob("*.json")).read_text()
    artifact = json.loads(raw)
    assert secret not in raw
    assert "private_metric" not in raw and "private_attribute" not in raw
    assert artifact["passed"] is passed
    assert artifact["cases"][0]["usage"]["input_tokens"] == 12
    assert len(artifact["dataset_version"]) == 64
    assert artifact["cost_usd"] is None


@pytest.mark.asyncio
async def test_paid_runners_require_opt_in(tmp_path: Path) -> None:
    """Reject accidental calls before constructing a provider or loading credentials."""
    for call in (
        evaluate_orchestrator_dataset("unused", tmp_path, scoring="deterministic"),
        evaluate_invoices_dataset("unused", tmp_path, scoring="deterministic"),
        evaluate_user_message_dataset(),
    ):
        with pytest.raises(ValueError, match="explicit live=True"):
            await call
