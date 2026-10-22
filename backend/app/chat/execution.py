"""Purpose: Bound AI work across parent and child runs and classify safe failures.

Public API:
- TurnBudget
- current_turn_budget
- budget_capabilities
- production_model
- model_settings
- public_chat_error
- prompt_versions
"""

import hashlib
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path

import httpx
from openai import AsyncOpenAI
from pydantic_ai import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded, RunContext
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.messages import ModelResponse
from pydantic_ai.capabilities import Hooks
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import GuardrailResult, ToolGuardrail
from pydantic_ai_harness.guardrails import ToolCallInfo

from app.config import Settings


@dataclass
class TurnBudget:
    """One request-scoped counter shared by all concurrent parent and child work."""

    settings: Settings
    requests: int = 0
    tools: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def limits(self) -> UsageLimits:
        """Return framework limits in addition to authoritative hook counters."""
        return UsageLimits(request_limit=self.settings.chat_request_limit,
            tool_calls_limit=self.settings.chat_tool_limit, total_tokens_limit=self.settings.chat_token_limit)


current_turn_budget: ContextVar[TurnBudget | None] = ContextVar("current_turn_budget", default=None)


def model_settings(settings: Settings, *, summary: bool = False) -> ModelSettings:
    """Set provider output and request budgets, omitting unsupported temperature when unset."""
    values: ModelSettings = {
        "max_tokens": settings.summary_output_limit if summary else settings.chat_output_limit,
        "timeout": settings.ai_request_timeout_seconds,
        "parallel_tool_calls": False,
    }
    if settings.chat_temperature is not None:
        values["temperature"] = settings.chat_temperature
    return values


def production_model(settings: Settings) -> tuple[OpenAIChatModel, AsyncOpenAI]:
    """Build the supported OpenAI provider with SDK retries disabled and owned cleanup."""
    if not settings.model.startswith("openai:"):
        raise ValueError("Production MODEL must use the supported openai: provider")
    client = AsyncOpenAI(max_retries=settings.ai_provider_retries, timeout=settings.ai_request_timeout_seconds)
    return OpenAIChatModel(settings.model.removeprefix("openai:"), provider=OpenAIProvider(openai_client=client)), client


async def _before_request(ctx: RunContext, request_context: ModelRequestContext) -> ModelRequestContext:
    """Reserve a model call before it starts, including calls hidden inside delegations."""
    budget = current_turn_budget.get()
    if budget is None:
        return request_context
    if budget.requests >= budget.settings.chat_request_limit:
        raise UsageLimitExceeded("Shared model request budget exhausted")
    remaining = budget.settings.chat_token_limit - budget.input_tokens - budget.output_tokens
    if remaining <= 0:
        raise UsageLimitExceeded("Shared token budget exhausted")
    budget.requests += 1
    values = model_settings(budget.settings)
    values["max_tokens"] = min(values["max_tokens"], remaining)
    return replace(request_context, model_settings={**(request_context.model_settings or {}), **values})


async def _after_request(ctx: RunContext, *, request_context: ModelRequestContext, response: ModelResponse) -> ModelResponse:
    """Check returned usage before another tool or model call can act on the response."""
    budget = current_turn_budget.get()
    if budget is not None:
        budget.input_tokens += response.usage.input_tokens
        budget.output_tokens += response.usage.output_tokens
        if response.usage.output_tokens > budget.settings.chat_output_limit:
            raise UsageLimitExceeded("Model output budget exhausted")
        if budget.input_tokens + budget.output_tokens > budget.settings.chat_token_limit:
            raise UsageLimitExceeded("Shared token budget exhausted")
    return response


def _before_tool(info: ToolCallInfo) -> GuardrailResult:
    """Reserve each delegated or MCP tool call without retaining its arguments."""
    budget = current_turn_budget.get()
    if budget is not None:
        if budget.tools >= budget.settings.chat_tool_limit:
            raise UsageLimitExceeded("Shared tool budget exhausted")
        budget.tools += 1
    return GuardrailResult.allow()


def budget_capabilities() -> list[object]:
    """Attach the same authoritative counters to both agents without double inheritance."""
    return [Hooks(before_model_request=_before_request, after_model_request=_after_request),
            ToolGuardrail(guard=_before_tool)]


def public_chat_error(error: Exception) -> str:
    """Map failures to recoverable client guidance without provider messages or request data."""
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            if isinstance(nested, (BaseExceptionGroup, TimeoutError, httpx.TransportError,
                                   UsageLimitExceeded, ModelHTTPError, UnexpectedModelBehavior)):
                return public_chat_error(nested)
    suffix = " Saved proposals remain pending; reopen this conversation to review them."
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "The assistant timed out. Try a shorter request." + suffix
    if isinstance(error, UsageLimitExceeded):
        return "The assistant reached its work limit. Try a narrower request." + suffix
    if isinstance(error, ModelHTTPError) and error.status_code == 429:
        return "The model provider is busy. Wait briefly and try again." + suffix
    if isinstance(error, (ModelHTTPError, httpx.TransportError)):
        return "The model provider is unavailable. Try again shortly." + suffix
    if isinstance(error, UnexpectedModelBehavior):
        return "The assistant could not produce a valid answer. Rephrase your request." + suffix
    return "The assistant could not finish this request. Try again." + suffix


def prompt_versions() -> dict[str, str]:
    """Hash prompt and screening source versions without exposing any injected values."""
    root = Path(__file__).parent
    return {name: hashlib.sha256((root / path).read_bytes()).hexdigest() for name, path in {
        "report": "report_prompt.py", "chat": "prompt.py", "summary": "summary.py", "guardrail": "guardrails/policy_screen.py",
    }.items()}
