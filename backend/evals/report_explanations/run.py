"""Purpose: Evaluate source-backed report rendering offline and separately opt-in selector/judge quality.

Public API:
- synthetic_facts
- run_golden
- run_judge
- main
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from app.chat.execution import TurnBudget, current_turn_budget, model_settings, production_model, prompt_versions
from app.chat.guardrails.pii import PiiVault, current_vault
from app.chat.guardrails.redaction import redact_text
from app.chat.report_agent import build_report_agent
from app.chat.report_facts import ReportFactSelection, ReportFacts, current_report_facts
from app.config import get_settings
from app.mcp_server.server import build_mcp_server
from app.reports.comparison import compare_profit_and_loss
from app.reports.models import BalanceSheetReport, FinancialReport, ReportRow
from app.reports.balance_sheet import compare_balance_sheets

ROOT = Path(__file__).parent


def synthetic_facts(case: dict) -> ReportFacts:
    """Build validated synthetic source trees without importing test fixtures or calling Xero."""
    if case.get("report_type") == "balance_sheet":
        return synthetic_position_facts(case)
    def source(index: int) -> FinancialReport:
        """Create one labelled accrual period with exact reconciled totals."""
        income = Decimal(case["income"][index])
        expense = sum((Decimal(pair[index]) for pair in case["expenses"]), Decimal(0))
        income_row = ReportRow(key="income", kind="account", label="Synthetic sales", amount=str(income), account_id="synthetic-income")
        expenses = [ReportRow(key=f"expense-{number}", kind="account", label=f"Expense {number}", amount=pair[index], account_id=f"synthetic-expense-{number}")
                    for number, pair in enumerate(case["expenses"], 1)]
        return FinancialReport(status="ready", date_from="2026-02-01" if index == 0 else "2026-01-01", date_to="2026-02-28" if index == 0 else "2026-01-31",
                               currency="AUD", currency_decimal_places=2, timezone="UTC", retrieved_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
                               rows=[ReportRow(key="sales", kind="section", label="Trading Income", children=[income_row]),
                                     ReportRow(key="expenses", kind="section", label="Operating Expenses", children=expenses),
                                     ReportRow(key="profit", kind="summary", label="Net Profit", amount=str(income - expense))])
    report = compare_profit_and_loss(source(0), source(1))
    selected = next(row.key for row in report.movements if row.label == "Expense 1") if case.get("selected") else None
    return ReportFacts(report, selected, "synthetic-selection")


def synthetic_position_facts(case: dict) -> ReportFacts:
    """Create reconciled synthetic positions for position-versus-flow quality checks."""
    def position(index: int) -> BalanceSheetReport:
        """Build independently dated account sources with all accounting totals."""
        rows = []
        for category in ("assets", "liabilities", "equity"):
            amount = case[category][index]
            rows.append(ReportRow(key=category, kind="section", label=category.capitalize(), children=[
                ReportRow(key=category + "-account", kind="account", label="Synthetic " + category, amount=amount, account_id="synthetic-" + category),
                ReportRow(key=category + "-total", kind="summary", label="Total " + category.capitalize(), amount=amount)]))
        rows.append(ReportRow(key="net-assets", kind="summary", label="Net Assets", amount=str(Decimal(case["assets"][index]) - Decimal(case["liabilities"][index]))))
        return BalanceSheetReport(status="ready", as_of="2026-02-28" if index == 0 else "2026-01-31", currency="AUD", currency_decimal_places=2,
                                  timezone="UTC", retrieved_at=datetime(2026, 3, 1, tzinfo=timezone.utc), rows=rows)
    return ReportFacts(compare_balance_sheets(position(0), position(1)), None, "synthetic-position-selection")


def run_golden() -> list[dict]:
    """Fail CI for incomplete, duplicated or failed exact numeric/source/uncertainty cases."""
    cases = json.loads((ROOT / "deterministic.json").read_text())
    if not cases or len({case["name"] for case in cases}) != len(cases):
        raise AssertionError("Golden cases must be nonempty and unique")
    results = []
    for case in cases:
        if not case.get("contains"):
            raise AssertionError("Golden cases require exact assertions")
        facts = synthetic_facts(case)
        answer = facts.render(ReportFactSelection(focus=case.get("focus", "overview")))
        checks = [value in answer for value in case["contains"]]
        checks += ["/performance?context=" in answer, "2026-03-01" in answer, "synthetic-expense" not in answer]
        passed = bool(checks) and all(checks)
        results.append({"case": case["name"], "passed": passed})
        if not passed:
            raise AssertionError(f"Report golden case failed: {case['name']}")
    return results


class JudgeVerdict(BaseModel):
    """A typed approval carries no retained answer or judge-written financial prose."""

    model_config = ConfigDict(extra="forbid")
    passes: bool


async def run_judge(*, live: bool) -> list[dict]:
    """Opt in to bounded paid selection and separate judging on synthetic cases only."""
    if not live:
        raise ValueError("Judge evaluations require --live")
    settings = get_settings().model_copy(update={"model": get_settings().report_model})
    cases = json.loads((ROOT / "judge.json").read_text())
    if not cases or len({case["name"] for case in cases}) != len(cases):
        raise ValueError("Judge cases must be nonempty and unique")
    model, client = production_model(settings)
    results = []
    try:
        async with asyncio.timeout(900):
            for case in cases:
                async with asyncio.timeout(60):
                    facts = synthetic_facts(case)
                    marker = current_report_facts.set(facts)
                    vault_marker = current_vault.set(PiiVault())
                    budget_marker = current_turn_budget.set(TurnBudget(settings))
                    try:
                        agent = build_report_agent(model, build_mcp_server(), settings)
                        selection = await agent.run(redact_text(case["question"]), usage_limits=current_turn_budget.get().limits(), model_settings=model_settings(settings))
                        answer = facts.render(selection.output)
                        judge = Agent(model, output_type=JudgeVerdict, retries=1, instructions="Judge synthetic report fidelity against the supplied rubric. Return only passes.")
                        async with asyncio.timeout(20):
                            verdict = await judge.run(json.dumps({"rubric": case["rubric"], "answer": answer}), usage_limits=UsageLimits(request_limit=2, total_tokens_limit=2000), model_settings=model_settings(settings))
                        results.append({"case": case["name"], "passed": verdict.output.passes})
                    finally:
                        current_report_facts.reset(marker)
                        current_vault.reset(vault_marker)
                        current_turn_budget.reset(budget_marker)
    finally:
        await client.close()
    if len(results) != len(cases) or not results or not all(item["passed"] for item in results):
        raise AssertionError("Report judge dataset failed or is incomplete")
    return results


def main() -> None:
    """Run offline goldens by default; write only safe metadata for explicit paid judge runs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scoring", choices=["deterministic", "judge"], default="deterministic")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    results = run_golden() if args.scoring == "deterministic" else asyncio.run(run_judge(live=args.live))
    if args.scoring == "judge":
        artifacts = ROOT.parent / "artifacts"
        artifacts.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        (artifacts / f"report-{stamp}.json").write_text(json.dumps({"cases": results, "model": get_settings().report_model, "prompt_versions": prompt_versions(), "cost_available": False}))
    print(json.dumps({"cases": results, "passed": all(item["passed"] for item in results)}))


if __name__ == "__main__":
    main()
