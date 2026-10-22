"""Purpose: Buffer typed report selection and emit only application-rendered, verified SSE text.

Public API:
- report_chat_response
"""

import asyncio
import json
import uuid
from contextlib import ExitStack

from fastapi import Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.chat.execution import TurnBudget, current_turn_budget, model_settings, production_model, prompt_versions
from app.chat.guardrails.pii import PiiVault, current_vault
from app.chat.guardrails.redaction import redact_text
from app.chat.guardrails.phrase_screen import screen_known_phrases
from app.chat.guardrails.policy_screen import current_jev, screener_for
from app.chat.report_agent import build_report_agent
from app.chat.report_prompt import REPORT_PROMPT
from app.chat.report_history import REPORT_HISTORY_NOTICE
from app.chat.report_facts import ReportFacts, current_report_facts
from app.errors import ApiError
from app.observability import conversation_pseudonym, trace_ai_work
from app.runtime import current_services, current_conversation_id


class ReportContextInput(BaseModel):
    """Bound the opaque signed token independently from untrusted chat history."""

    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=2048)


def _event(value: dict) -> str:
    """Encode only application-controlled Vercel stream records."""
    return "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"


async def report_chat_response(request: Request, token: object, question: str, deadline: float) -> StreamingResponse:
    """Resolve fresh evidence and privately validate selection before any text reaches the browser."""
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled.", False, "Open Performance after reporting is enabled.")
    try:
        context_input = ReportContextInput(token=token)
    except ValidationError as error:
        raise ApiError(422, "Report selection is invalid", "A bounded signed report selection is required.", False, "Reopen Performance.") from error
    request.app.state.report_contexts.parse(context_input.token)
    if not question.strip() or len(question) > settings.chat_prompt_character_limit:
        raise ApiError(422, "Report question is invalid", "A bounded question is required.", False, "Shorten the question and try again.")
    conversation = request.headers.get("x-conversation-id") or str(uuid.uuid4())
    services = request.app.state.services
    report_settings = settings.model_copy(update={"model": settings.report_model, "jev_model": settings.report_jev_model})
    budget = TurnBudget(report_settings)
    vault = PiiVault()

    async def encode():
        """Keep report state request-local and never stream model prose or partial typed output."""
        message_id = str(uuid.uuid4())
        yield _event({"type": "start", "messageId": message_id})
        with ExitStack() as stack:
            for variable, value in ((current_services, services), (current_conversation_id, conversation), (current_vault, vault),
                                    (current_turn_budget, budget), (current_jev, screener_for(report_settings))):
                stack.callback(variable.reset, variable.set(value))
            with trace_ai_work("report_explanation", report_settings, conversation_pseudonym(conversation, settings.session_secret), prompt_versions()) as span:
                span.set_attribute("gen_ai.request.model", settings.report_model)
                try:
                    async with asyncio.timeout_at(deadline):
                        report, selected = await request.app.state.report_contexts.resolve(context_input.token, services.reports)
                        facts = ReportFacts(report, selected, context_input.token)
                        stack.callback(current_report_facts.reset, current_report_facts.set(facts))
                        selection = None
                        fallback = True
                        protected = facts.protected_input(redact_text)
                        protected_question = redact_text(question)
                        labels = json.dumps(protected, ensure_ascii=False)
                        safe = len(labels) + len(protected_question) + len(REPORT_PROMPT) <= settings.report_model_character_limit and screen_known_phrases(labels).action == "allow" and screen_known_phrases(protected_question).action == "allow"
                        screener = current_jev.get()
                        if safe and settings.report_narration_enabled and screener is not None:
                            try:
                                with trace_ai_work("report_label_guard", report_settings, conversation_pseudonym(conversation, settings.session_secret), prompt_versions()) as guard_span:
                                    guard_span.set_attribute("gen_ai.request.model", settings.report_jev_model)
                                    try:
                                        safe = await asyncio.wait_for(screener.guard(labels, "input"), settings.jev_timeout_seconds) == "pass"
                                    except Exception:
                                        guard_span.set_attribute("ledger.outcome", "fallback")
                                        raise
                                    guard_span.set_attribute("ledger.outcome", "allow" if safe else "fallback")
                            except Exception:
                                safe = False
                        if safe and settings.report_narration_enabled:
                            client = None
                            try:
                                model = request.app.state.report_model
                                if model is None:
                                    model, client = production_model(report_settings)
                                agent = build_report_agent(model, request.app.state.mcp_server, report_settings)
                                remaining = deadline - asyncio.get_running_loop().time() - 1
                                if remaining <= 0:
                                    raise TimeoutError("No report selection time remains")
                                async with asyncio.timeout(remaining):
                                    result = await agent.run(protected_question, usage_limits=budget.limits(), model_settings=model_settings(report_settings))
                                selection = result.output
                                fallback = False
                            except Exception:
                                selection = None
                            finally:
                                if client is not None:
                                    await client.close()
                        text = facts.render(selection, fallback)
                        await asyncio.to_thread(services.actions.ensure_conversation, conversation)
                        await asyncio.to_thread(services.actions.add_message, conversation, "user", question)
                        # Retain only a refresh notice; free-prose history must never receive report figures.
                        await asyncio.to_thread(services.actions.add_message, conversation, "assistant", REPORT_HISTORY_NOTICE)
                        span.set_attribute("ledger.outcome", "fallback" if fallback else "complete")
                except asyncio.CancelledError:
                    span.set_attribute("ledger.outcome", "cancelled")
                    raise
                except ApiError as error:
                    text = f"{error.what}. {error.next_step} No report figures were inferred."
                    span.set_attribute("ledger.outcome", "unavailable")
                except Exception:
                    text = "The report explanation is unavailable. Reopen Performance and try again. No report figures were inferred."
                    span.set_attribute("ledger.outcome", "error")
                finally:
                    span.set_attribute("ledger.requests", budget.requests)
                    span.set_attribute("ledger.tools", budget.tools)
                    span.set_attribute("ledger.input_tokens", budget.input_tokens)
                    span.set_attribute("ledger.output_tokens", budget.output_tokens)
            yield _event({"type": "text-start", "id": message_id})
            yield _event({"type": "text-delta", "id": message_id, "delta": text})
            yield _event({"type": "text-end", "id": message_id})
            yield _event({"type": "finish"})
            yield "data: [DONE]\n\n"

    return StreamingResponse(encode(), media_type="text/event-stream", headers={"x-vercel-ai-ui-message-stream": "v1", "Cache-Control": "no-cache, no-transform", "X-Conversation-Id": conversation})
