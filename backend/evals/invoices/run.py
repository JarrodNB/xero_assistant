"""Purpose: Load one invoices dataset and score that agent.

Public API:
- DETERMINISTIC_PATH
- JUDGE_PATH
- evaluate_invoices_dataset
- load_invoices_dataset
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from app.chat.invoices_agent import build_invoices_agent
from app.config import get_settings
from app.mcp_server.server import build_mcp_server
from evals.checks import DoesNotClaimUnconfirmedWrite
from evals.invoices.evaluators import ExpectedRead, FinancialAnswer
from evals.invoices.fixtures import financial_gateway
from evals.scoring import Scoring
from evals.reporting import evaluate_dataset, live_cli
from evals.turn import run_scored_prompt

DETERMINISTIC_PATH = Path(__file__).with_name("deterministic.yaml")
JUDGE_PATH = Path(__file__).with_name("judge.yaml")


def load_invoices_dataset(scoring: Scoring) -> Dataset:
    """Load the invoices deterministic cases or the judge cases."""
    if scoring == "deterministic":
        return Dataset[str, str, Any].from_file(
            DETERMINISTIC_PATH,
            custom_evaluator_types=[DoesNotClaimUnconfirmedWrite, ExpectedRead, FinancialAnswer],
        )
    dataset = Dataset[str, str, Any].from_file(JUDGE_PATH)
    dataset.evaluators.append(DoesNotClaimUnconfirmedWrite())
    return dataset


async def evaluate_invoices_dataset(model, directory: Path, *, scoring: Scoring, case_names: set[str] | None = None, live: bool = False) -> EvaluationReport:
    """Score the invoices agent from the deterministic dataset or the judge dataset."""
    if not live:
        raise ValueError("Paid evaluations require explicit live=True or CLI --live")
    dataset = load_invoices_dataset(scoring)
    if case_names is not None:
        dataset.cases = [case for case in dataset.cases if case.name in case_names]
        if {case.name for case in dataset.cases} != case_names:
            raise ValueError("Unknown invoices evaluation case name")
    agent = build_invoices_agent(model, build_mcp_server())
    scenarios = {case.inputs: (case.metadata or {}).get("financial_scenario") for case in dataset.cases}

    async def answer(prompt: str) -> str:
        """Answer one invoices case without writing to Xero."""
        gateway = financial_gateway(scenarios[prompt])
        return await asyncio.wait_for(run_scored_prompt(agent, gateway, directory, prompt), timeout=90)

    return await evaluate_dataset(dataset, answer, live=live,
        dataset_path=DETERMINISTIC_PATH if scoring == "deterministic" else JUDGE_PATH,
        model=str(model), prompt_paths=[Path("app/chat/prompt.py")])


def main() -> None:
    """Score one explicitly selected live invoices dataset."""
    args = live_cli()
    with tempfile.TemporaryDirectory() as directory:
        asyncio.run(evaluate_invoices_dataset(get_settings().model, Path(directory),
            scoring=args.scoring, case_names=set(args.case_names) if args.case_names else None, live=True))
    print("Evaluation passed; safe metadata saved under evals/artifacts.")


if __name__ == "__main__":
    main()
