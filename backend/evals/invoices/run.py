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
from evals.invoices.evaluators import ExpectedRead
from evals.scoring import Scoring
from evals.turn import run_scored_prompt
from tests.fakes import FakeInvoiceGateway

DETERMINISTIC_PATH = Path(__file__).with_name("deterministic.yaml")
JUDGE_PATH = Path(__file__).with_name("judge.yaml")


def load_invoices_dataset(scoring: Scoring) -> Dataset:
    """Load the invoices deterministic cases or the judge cases."""
    if scoring == "deterministic":
        return Dataset[str, str, Any].from_file(
            DETERMINISTIC_PATH,
            custom_evaluator_types=[DoesNotClaimUnconfirmedWrite, ExpectedRead],
        )
    return Dataset[str, str, Any].from_file(JUDGE_PATH)


async def evaluate_invoices_dataset(model, directory: Path, *, scoring: Scoring) -> EvaluationReport:
    """Score the invoices agent from the deterministic dataset or the judge dataset."""
    dataset = load_invoices_dataset(scoring)
    agent = build_invoices_agent(model, build_mcp_server())
    gateway = FakeInvoiceGateway()

    async def answer(prompt: str) -> str:
        """Answer one invoices case without writing to Xero."""
        return await run_scored_prompt(agent, gateway, directory, prompt)

    return await dataset.evaluate(answer)


def main() -> None:
    """Score the invoices deterministic dataset, then the judge dataset."""
    settings = get_settings()
    scorings: tuple[Scoring, ...] = ("deterministic", "judge")
    for scoring in scorings:
        with tempfile.TemporaryDirectory() as directory:
            report = asyncio.run(evaluate_invoices_dataset(settings.model, Path(directory), scoring=scoring))
        print(scoring)
        report.print()


if __name__ == "__main__":
    main()
