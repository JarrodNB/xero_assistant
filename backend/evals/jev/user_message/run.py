"""Purpose: Load the user-message dataset and score that Jev screen.

Public API:
- DETERMINISTIC_PATH
- evaluate_user_message_dataset
- load_user_message_dataset
"""

import asyncio
from pathlib import Path
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from app.chat.guardrails.policy_screen import screener_for
from app.config import get_settings

DETERMINISTIC_PATH = Path(__file__).with_name("deterministic.yaml")


def load_user_message_dataset() -> Dataset:
    """Load the user-message cases and their expected actions."""
    return Dataset[str, str, Any].from_file(DETERMINISTIC_PATH)


async def evaluate_user_message_dataset() -> EvaluationReport:
    """Score the configured Jev model on the user-message screen."""
    screener = screener_for(get_settings())
    if screener is None:
        raise RuntimeError("TYPESAFE_API_KEY is required to score the user-message dataset.")
    dataset = load_user_message_dataset()

    async def answer(prompt: str) -> str:
        """Return the strict-policy action for one user message."""
        return await screener.guard(prompt, "input")

    return await dataset.evaluate(answer)


def main() -> None:
    """Score the user-message dataset."""
    report = asyncio.run(evaluate_user_message_dataset())
    report.print()


if __name__ == "__main__":
    main()
