"""Purpose: Stream a chat turn and read stored conversation history.

Public API:
- router
- STREAM_HEADERS
- latest_user_text
"""

import json
import uuid
import asyncio
from contextlib import ExitStack, aclosing
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

from app.auth.routes import require_user
from app.actions.service import load_action
from app.chat.guardrails.context import GuardrailMessage, current_guardrail_context, prepare_guardrail_input
from app.chat.guardrails.pii import OutboundRestorer, PiiVault, current_vault
from app.chat.guardrails.policy_screen import current_jev, screener_for
from app.chat.guardrails.redaction import prepare_run_input
from app.chat.summary import current_history_summary, summarize_with_model, update_stored_summary
from app.chat.execution import TurnBudget, current_turn_budget, model_settings, public_chat_error, prompt_versions
from app.observability import conversation_pseudonym, trace_ai_work
from app.db.repository import StoredAction, StoredMessage
from app.errors import ApiError
from app.runtime import current_conversation_id, current_services
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

router = APIRouter(tags=["chat"])

STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",
}


def _timestamp(value: datetime) -> str:
    """Serialize a stored time for the chat client."""
    return value.isoformat()


def _message_payload(message: StoredMessage) -> dict[str, str]:
    """Serialize one stored message."""
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "created_at": _timestamp(message.created_at),
    }


def _action_payload(action: StoredAction) -> dict[str, object]:
    """Serialize one proposed action for a confirmation card."""
    return {
        "kind": "proposed_action",
        "action_id": action.id,
        "action_type": action.action_type,
        "status": action.status,
        "summary": action.summary,
        "payload": action.payload,
        "created_at": _timestamp(action.created_at),
    }


@router.get("/conversations")
def list_conversations(request: Request) -> dict[str, object]:
    """Return stored chats, newest activity first."""
    require_user(request)
    conversations = request.app.state.services.actions.list_conversations()
    return {
        "conversations": [
            {
                "id": item.id,
                "updated_at": _timestamp(item.updated_at),
                "preview": item.preview,
            }
            for item in conversations
        ]
    }


@router.get("/conversations/{conversation_id}")
def read_conversation(conversation_id: str, request: Request) -> dict[str, object]:
    """Return one thread's messages and proposed actions."""
    require_user(request)
    found = request.app.state.services.actions.get_conversation(conversation_id)
    if found is None:
        raise ApiError(
            404,
            "Conversation does not exist",
            "That chat could not be found.",
            False,
            "Open another conversation from the list.",
        )
    messages, actions = found
    actions = [
        load_action(request.app.state.services.actions, action.id, request.app.state.settings.action_execution_timeout_seconds)
        if action.status == "executing" else action
        for action in actions
    ]
    return {
        "id": conversation_id,
        "messages": [_message_payload(message) for message in messages],
        "actions": [_action_payload(action) for action in actions],
    }


def latest_user_text(body: bytes) -> str:
    """Pull the newest user text out of a Vercel AI chat request."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ""
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        parts = message.get("parts")
        if isinstance(parts, list):
            texts = [
                str(part.get("text") or "")
                for part in parts
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            joined = "\n".join(text for text in texts if text)
            if joined:
                return joined
        content = message.get("content")
        if isinstance(content, str) and content:
            return content
    return ""


@router.post("/chat")
async def chat(request: Request) -> Response:
    """Stream one bounded turn, including preparation and recoverable failure events."""
    require_user(request)
    settings = request.app.state.settings
    deadline = asyncio.get_running_loop().time() + settings.chat_timeout_seconds
    try:
        async with asyncio.timeout_at(deadline):
            body = await request.body()
            run_input = VercelAIAdapter.build_run_input(body)
    except (ValidationError, ValueError):
        return Response(content='{"what":"Invalid chat request"}', media_type="application/json", status_code=422)
    except TimeoutError:
        return Response(content='{"what":"Chat request timed out"}', media_type="application/json", status_code=408)
    conversation_id = request.headers.get("x-conversation-id") or str(uuid.uuid4())
    services = request.app.state.services
    user_text = latest_user_text(body)
    if len(user_text) > settings.chat_prompt_character_limit:
        return Response(content='{"what":"Chat message is too long; shorten the request"}',
                        media_type="application/json", status_code=422)
    vault = PiiVault()
    budget = TurnBudget(settings)
    adapter = VercelAIAdapter(agent=request.app.state.agent, run_input=run_input,
                             accept=request.headers.get("accept", SSE_CONTENT_TYPE))

    async def on_complete(result) -> None:
        """Store only successfully completed assistant text with personal data restored."""
        text = str(getattr(result, "output", ""))
        if text:
            await asyncio.to_thread(services.actions.add_message, conversation_id, "assistant", vault.restore_text(text))

    async def encode() -> AsyncIterator[str]:
        """Bound the complete workflow and reset all request context even on cancellation."""
        with ExitStack() as context:
            for variable, value in ((current_services, services), (current_conversation_id, conversation_id),
                                    (current_vault, vault), (current_turn_budget, budget),
                                    (current_jev, screener_for(settings))):
                context.callback(variable.reset, variable.set(value))
            with trace_ai_work("chat", settings, conversation_pseudonym(conversation_id, settings.session_secret), prompt_versions()) as span:
                try:
                    async with asyncio.timeout_at(deadline):
                        await asyncio.to_thread(services.actions.ensure_conversation, conversation_id)
                        previous = (await asyncio.to_thread(services.actions.list_messages, conversation_id))[-2:]
                        if user_text:
                            await asyncio.to_thread(services.actions.add_message, conversation_id, "user", user_text)

                        async def summarize(prompt: str) -> str:
                            """Bound each protected summary attempt separately from chat usage."""
                            async with asyncio.timeout(settings.summary_timeout_seconds):
                                with trace_ai_work("summary", settings, conversation_pseudonym(conversation_id, settings.session_secret), prompt_versions()):
                                    return await summarize_with_model(request.app.state.ai_model or settings.model, prompt, settings)

                        history = await update_stored_summary(services.actions, conversation_id, settings.chat_summary_every,
                            summarize, max_blocks=settings.summary_max_blocks, recent_limit=settings.history_message_limit,
                            character_limit=settings.history_character_limit)
                        context.callback(current_history_summary.reset, current_history_summary.set(history))
                        prepared = await asyncio.to_thread(prepare_guardrail_input, user_text, [
                            GuardrailMessage(role="assistant" if message.role == "assistant" else "user", content=message.content)
                            for message in previous if message.role in {"user", "assistant"}])
                        context.callback(current_guardrail_context.reset, current_guardrail_context.set(prepared.context))
                        await asyncio.to_thread(prepare_run_input, run_input)

                        async def safe_native():
                            """Sanitize errors before the adapter converts them into client events."""
                            try:
                                async with aclosing(adapter.run_stream_native(usage_limits=budget.limits(),
                                        model_settings=model_settings(settings))) as events:
                                    async for event in events:
                                        yield event
                                span.set_attribute("ledger.outcome", "complete")
                            except Exception as error:
                                span.set_attribute("ledger.outcome", "error")
                                raise RuntimeError(public_chat_error(error)) from None

                        restorer = OutboundRestorer(vault)
                        native = safe_native()
                        events = adapter.transform_stream(native, on_complete=on_complete)
                        async with aclosing(native), aclosing(events), aclosing(adapter.encode_stream(events)) as encoded:
                            async for chunk in encoded:
                                restored = restorer.push(chunk)
                                if restored:
                                    yield restored
                        tail = restorer.finish()
                        if tail:
                            yield tail
                except asyncio.CancelledError:
                    span.set_attribute("ledger.outcome", "cancelled")
                    raise
                except Exception as error:
                    # Do not flush a partial protected token from an interrupted response.
                    span.set_attribute("ledger.outcome", "error")
                    yield "data: " + json.dumps({"type": "error", "errorText": public_chat_error(error)}) + "\n\n"
                    yield "data: [DONE]\n\n"
                finally:
                    span.set_attribute("ledger.requests", budget.requests)
                    span.set_attribute("ledger.tools", budget.tools)
                    span.set_attribute("ledger.input_tokens", budget.input_tokens)
                    span.set_attribute("ledger.output_tokens", budget.output_tokens)

    return StreamingResponse(encode(), media_type=SSE_CONTENT_TYPE,
        headers={**STREAM_HEADERS, "X-Conversation-Id": conversation_id})
