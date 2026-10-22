"""Purpose: Keep separate report golden and judge evaluation cases useful and offline by default.

Public API:
- Offline report evaluation regressions
"""

import json

import pytest

from app.chat.report_facts import ReportFactSelection
from evals.report_explanations.run import ROOT, run_golden, run_judge, synthetic_facts


def test_report_golden_dataset_preserves_amounts_sources_and_uncertainty():
    """Every separate golden case has exact assertions and must pass without providers."""
    result = run_golden()
    assert len(result) >= 6 and all(case["passed"] for case in result)
    assert {case["case"] for case in result} != {case["name"] for case in json.loads((ROOT / "judge.json").read_text())}


@pytest.mark.asyncio
async def test_report_judging_requires_explicit_paid_opt_in():
    """No accidental provider request is possible from the default runner path."""
    with pytest.raises(ValueError, match="require --live"):
        await run_judge(live=False)


def test_remainder_matches_actually_displayed_accounts_and_offered_keys():
    """Seven movements reconcile; guessed unoffered indices are never valid model evidence."""
    case = next(case for case in json.loads((ROOT / "deterministic.json").read_text()) if case["name"] == "seven_movements")
    facts = synthetic_facts(case)
    assert len(facts.report.movements) == 7
    assert len(facts.offered_keys() - set(facts.report.metrics)) == 5
    assert "not displayed above: -300.00 AUD" in facts.render()
    selected = facts.report.top_movements[0]
    text = facts.render(ReportFactSelection(evidence=[selected.key]))
    from decimal import Decimal
    expected = Decimal(facts.report.metrics["net_profit"].change) - Decimal(selected.contribution)
    assert f"not displayed above: {expected} AUD" in text
