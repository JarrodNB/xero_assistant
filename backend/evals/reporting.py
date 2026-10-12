"""Purpose: Validate complete evaluation reports and retain safe run evidence.

Public API:
- assert_report_integrity
- evaluate_dataset
- live_cli
"""

import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Callable

from pydantic_evals.reporting import EvaluationReport
from pydantic_evals.evaluators import GEval, LLMJudge

ARTIFACT_DIRECTORY = Path(__file__).with_name("artifacts")


def assert_report_integrity(report: EvaluationReport, expected_names: list[str]) -> None:
    """Require exactly the selected cases, successful assertions, and no execution errors."""
    if not expected_names or len(set(expected_names)) != len(expected_names):
        raise AssertionError("Selected dataset must contain unique named cases")
    if report.failures:
        raise AssertionError("Evaluation task execution failed")
    if getattr(report, "report_evaluator_failures", []):
        raise AssertionError("Report evaluator execution failed")
    names = [case.name for case in report.cases]
    if sorted(names) != sorted(expected_names):
        raise AssertionError("Evaluation report is empty, incomplete, duplicated, or unexpected")
    for case in report.cases:
        if case.evaluator_failures:
            raise AssertionError(f"Evaluator execution failed for {case.name}")
        if not case.assertions:
            raise AssertionError(f"No evaluator assertions for {case.name}")
        if any(item.value is not True for item in case.assertions.values()):
            raise AssertionError(f"Evaluator assertion failed for {case.name}")


async def evaluate_dataset(dataset, answer: Callable, *, live: bool, dataset_path: Path,
                           model: str, prompt_paths: list[Path]) -> EvaluationReport:
    """Opt in to bounded paid work and save only allowlisted metadata, never case text."""
    if not live:
        raise ValueError("Paid evaluations require explicit live=True or CLI --live")
    expected_names = [case.name for case in dataset.cases]
    if not expected_names or len(set(expected_names)) != len(expected_names):
        raise ValueError("Select at least one uniquely named evaluation case")
    judges = [evaluator for evaluator in dataset.evaluators
              if isinstance(evaluator, (GEval, LLMJudge))]
    judges.extend(evaluator for case in dataset.cases for evaluator in case.evaluators
                  if isinstance(evaluator, (GEval, LLMJudge)))
    for judge in judges:
        judge.model = model
    started = datetime.now(timezone.utc)
    report = await asyncio.wait_for(dataset.evaluate(answer, max_concurrency=2), timeout=900)
    error = None
    try:
        assert_report_integrity(report, expected_names)
    except AssertionError as exc:
        error = str(exc)
    artifact = {
        "schema_version": 1,
        "started_at": started.isoformat(),
        "duration_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
        "configured_model": model,
        "configured_judge_model": model if judges else None,
        "model_snapshot_note": "Aliases are not immutable snapshots; task resolved models are recorded where available.",
        "framework_version": version("pydantic-evals"),
        "dataset_version": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "prompt_version": hashlib.sha256(b"".join(path.read_bytes() for path in prompt_paths)).hexdigest(),
        "passed": error is None,
        "integrity_error": error,
        "selected_cases": expected_names,
        "task_failure_count": len(report.failures),
        "cost_usd": None,
        "cost_note": "Unavailable: no provider billing data. Usage metrics cover task calls only, excluding judge and Jev billing; consult provider billing for total cost.",
        "cases": [{
            "name": case.name,
            "duration_seconds": case.task_duration,
            "total_duration_seconds": case.total_duration,
            "assertions": {name: item.value is True for name, item in case.assertions.items()},
            "evaluator_failure_count": len(case.evaluator_failures),
            "usage": {key: value for key, value in case.metrics.items() if key in {"input_tokens", "output_tokens", "requests", "tool_calls"}},
            "resolved_models": case.attributes.get("resolved_models", []),
        } for case in report.cases],
    }
    ARTIFACT_DIRECTORY.mkdir(exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%S%fZ")
    (ARTIFACT_DIRECTORY / f"{dataset.name}-{stamp}.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    if error:
        raise AssertionError(error)
    return report


def live_cli() -> argparse.Namespace:
    """Require a deliberate paid-run flag and allow a small selected-case smoke set."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--scoring", choices=["deterministic", "judge"], default="deterministic")
    parser.add_argument("--case", action="append", dest="case_names")
    return parser.parse_args()
