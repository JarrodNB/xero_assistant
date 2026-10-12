"""Purpose: Load one orchestrator dataset and score that agent.

Public API:
- DETERMINISTIC_PATH
- JUDGE_PATH
- evaluate_orchestrator_dataset
- load_orchestrator_dataset
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from app.chat.orchestrator import build_chat_agent
from app.config import get_settings
from app.invoices.records import ContactRecord
from app.mcp_server.server import build_mcp_server
from evals.checks import DoesNotClaimUnconfirmedWrite
from evals.orchestrator.evaluators import ExpectedDelegate
from evals.scoring import Scoring
from evals.turn import ConversationInput, run_scored_prompt
from tests.fakes import FakeInvoiceGateway

DETERMINISTIC_PATH = Path(__file__).with_name("deterministic.yaml")
JUDGE_PATH = Path(__file__).with_name("judge.yaml")


def load_orchestrator_dataset(scoring: Scoring) -> Dataset:
    """Load the orchestrator deterministic cases or the judge cases."""
    if scoring == "deterministic":
        return Dataset[str | ConversationInput, str, Any].from_file(
            DETERMINISTIC_PATH,
            custom_evaluator_types=[DoesNotClaimUnconfirmedWrite, ExpectedDelegate],
        )
    return Dataset[str | ConversationInput, str, Any].from_file(JUDGE_PATH)


async def evaluate_orchestrator_dataset(
    model, directory: Path, *, scoring: Scoring, case_names: set[str] | None = None
) -> EvaluationReport:
    """Score the orchestrator. Bob's Construction already exists, so a complete invoice can be proposed."""
    dataset = load_orchestrator_dataset(scoring)
    if case_names is not None:
        dataset.cases = [case for case in dataset.cases if case.name in case_names]
        if {case.name for case in dataset.cases} != case_names:
            raise ValueError("Unknown orchestrator evaluation case name")
    agent = build_chat_agent(model, build_mcp_server())
    gateway = FakeInvoiceGateway()
    gateway.contacts.append(ContactRecord(name="Bob's Construction", email="bob@example.com"))

    async def answer(prompt: str | ConversationInput) -> str:
        """Answer one orchestrator case without writing to Xero."""
        return await asyncio.wait_for(run_scored_prompt(agent, gateway, directory, prompt), timeout=90)

    return await dataset.evaluate(answer, max_concurrency=2)


def main() -> None:
    """Score the orchestrator deterministic dataset, then the judge dataset."""
    settings = get_settings()
    scorings: tuple[Scoring, ...] = ("deterministic", "judge")
    for scoring in scorings:
        with tempfile.TemporaryDirectory() as directory:
            report = asyncio.run(evaluate_orchestrator_dataset(settings.model, Path(directory), scoring=scoring))
        print(scoring)
        report.print()


if __name__ == "__main__":
    main()
