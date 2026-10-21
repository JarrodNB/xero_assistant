"""Purpose: Load the user-message dataset and score that Jev screen.

Public API:
- DETERMINISTIC_PATH
- EvaluationMessage
- UserMessageInput
- evaluate_user_message_dataset
- load_user_message_dataset
- screen_user_message_input
"""

import asyncio
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from app.chat.guardrails.context import (
    GuardrailMessage,
    current_guardrail_context,
    format_guardrail_input,
    prepare_guardrail_input,
)
from app.chat.guardrails.pii import PiiVault, current_vault
from app.chat.guardrails.policy_screen import JevScreener, screener_for
from app.config import get_settings
from evals.reporting import evaluate_dataset, live_cli

DETERMINISTIC_PATH = Path(__file__).with_name("deterministic.yaml")


class EvaluationMessage(BaseModel):
    """One preceding message in a user-message evaluation case."""

    role: Literal["user", "assistant"]
    content: str


class UserMessageInput(BaseModel):
    """The latest prompt and optional preceding conversation messages for Jev."""

    prompt: str
    previous_messages: list[EvaluationMessage] = Field(default_factory=list)


def load_user_message_dataset() -> Dataset[UserMessageInput, str, Any]:
    """Load the user-message cases and their expected actions."""
    return Dataset[UserMessageInput, str, Any].from_file(DETERMINISTIC_PATH)


async def screen_user_message_input(screener: JevScreener, case: UserMessageInput) -> str:
    """Protect and format one evaluation case, then return its Jev action."""
    vault_token = current_vault.set(PiiVault())
    try:
        prepared = prepare_guardrail_input(
            case.prompt,
            [
                GuardrailMessage(role=message.role, content=message.content)
                for message in case.previous_messages
            ],
        )
        context_token = current_guardrail_context.set(prepared.context)
        try:
            return await screener.guard(format_guardrail_input(prepared.prompt), "input")
        finally:
            current_guardrail_context.reset(context_token)
    finally:
        current_vault.reset(vault_token)


async def evaluate_user_message_dataset(*, live: bool = False, case_names: set[str] | None = None) -> EvaluationReport:
    """Score the configured Jev model on the user-message screen."""
    if not live:
        raise ValueError("Paid evaluations require explicit live=True or CLI --live")
    screener = screener_for(get_settings())
    if screener is None:
        raise RuntimeError("TYPESAFE_API_KEY is required to score the user-message dataset.")
    dataset = load_user_message_dataset()
    if case_names is not None:
        dataset.cases = [case for case in dataset.cases if case.name in case_names]
        if {case.name for case in dataset.cases} != case_names:
            raise ValueError("Unknown Jev evaluation case name")

    async def answer(raw_input: object) -> str:
        """Return the strict-policy action for one typed user-message case."""
        case = UserMessageInput.model_validate(raw_input)
        return await asyncio.wait_for(screen_user_message_input(screener, case), timeout=90)

    return await evaluate_dataset(dataset, answer, live=live, dataset_path=DETERMINISTIC_PATH,
        model=get_settings().jev_model, prompt_paths=[Path("app/chat/guardrails/policy_screen.py"), Path("app/chat/guardrails/context.py")])


def main() -> None:
    """Score the user-message dataset."""
    args = live_cli()
    if args.scoring != "deterministic":
        raise ValueError("Jev has only a deterministic dataset")
    asyncio.run(evaluate_user_message_dataset(live=True,
        case_names=set(args.case_names) if args.case_names else None))
    print("Evaluation passed; safe metadata saved under evals/artifacts.")


if __name__ == "__main__":
    main()
