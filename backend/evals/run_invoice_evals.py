"""Purpose: Load the invoice golden dataset and score the chat agent.

Public API:
- DATASET_PATH
- LIVE_KEY_PLACEHOLDER
- load_invoice_golden_dataset
- live_judge_enabled
- evaluate_invoice_dataset
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.evaluators import GEval, LLMJudge
from pydantic_evals.reporting import EvaluationReport

from app.chat.agent import build_chat_agent
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.mcp_server.server import build_mcp_server
from app.runtime import AppServices, current_conversation_id, current_services
from evals.evaluators import DoesNotClaimUnconfirmedWrite
from sqlalchemy.orm import sessionmaker
from tests.fakes import FakeInvoiceGateway

DATASET_PATH = Path(__file__).with_name("invoice_golden.yaml")
LIVE_KEY_PLACEHOLDER = "test-key"


def load_invoice_golden_dataset() -> Dataset:
    """Load the golden dataset, including its case-specific LLM judges."""
    return Dataset[str, str, Any].from_file(DATASET_PATH, custom_evaluator_types=[DoesNotClaimUnconfirmedWrite])


def live_judge_enabled() -> bool:
    """Return whether a real OpenAI key is available for LLMJudge."""
    import os

    key = os.environ.get("OPENAI_API_KEY", "")
    return bool(key) and key != LIVE_KEY_PLACEHOLDER


def _is_model_judge(evaluator: object) -> bool:
    """Return whether an evaluator calls a model."""
    return isinstance(evaluator, (LLMJudge, GEval))


def _without_model_judges(dataset: Dataset) -> Dataset:
    """Drop model judges so an offline run stays deterministic."""
    dataset.evaluators = [item for item in dataset.evaluators if not _is_model_judge(item)]
    for case in dataset.cases:
        case.evaluators = [item for item in (case.evaluators or []) if not _is_model_judge(item)]
    return dataset


async def evaluate_invoice_dataset(
    model,
    directory: Path,
    *,
    include_llm_judge: bool = True,
) -> EvaluationReport:
    """Run the golden dataset against an agent backed by the fake invoice gateway."""
    dataset = load_invoice_golden_dataset()
    if not include_llm_judge:
        dataset = _without_model_judges(dataset)
    server = build_mcp_server()
    agent = build_chat_agent(model, server)
    gateway = FakeInvoiceGateway()

    async def answer(prompt: str) -> str:
        """Answer one golden-dataset prompt without writing to Xero."""
        conversation_id = str(uuid.uuid4())
        repository = ActionRepository(sessionmaker(bind=create_engine_for(str(directory / f"{conversation_id}.db"))))
        repository.ensure_conversation(conversation_id)
        services = AppServices(invoices=gateway, actions=repository)
        services_token = current_services.set(services)
        conversation_token = current_conversation_id.set(conversation_id)
        try:
            result = await agent.run(prompt)
        finally:
            current_conversation_id.reset(conversation_token)
            current_services.reset(services_token)
        return str(result.output)

    return await dataset.evaluate(answer)


def main() -> None:
    """Score the golden dataset with the configured model."""
    import tempfile

    from app.config import get_settings

    settings = get_settings()
    with tempfile.TemporaryDirectory() as directory:
        report = asyncio.run(
            evaluate_invoice_dataset(settings.model, Path(directory), include_llm_judge=live_judge_enabled())
        )
    report.print()


if __name__ == "__main__":
    main()
