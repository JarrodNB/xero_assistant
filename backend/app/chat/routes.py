"""Purpose: Stream a chat turn and read stored conversation history.

Public API:
- router
- latest_user_text
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

from app.auth.routes import require_user
from app.chat.jev import current_jev, screener_for
from app.chat.summary import current_history_summary, summarize_with_model, update_stored_summary
from app.db.repository import StoredAction, StoredMessage
from app.errors import ApiError
from app.runtime import current_conversation_id, current_services
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

router = APIRouter(tags=["chat"])


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
    """Stream one assistant turn for the signed-in person."""
    require_user(request)
    body = await request.body()
    accept = request.headers.get("accept", SSE_CONTENT_TYPE)
    try:
        run_input = VercelAIAdapter.build_run_input(body)
    except ValidationError as error:
        return Response(content=error.json(), media_type="application/json", status_code=422)

    conversation_id = request.headers.get("x-conversation-id") or str(uuid.uuid4())
    services = request.app.state.services
    services.actions.ensure_conversation(conversation_id)
    user_text = latest_user_text(body)
    if user_text:
        services.actions.add_message(conversation_id, "user", user_text)
    async def summarize(prompt: str) -> str:
        """Fold one redacted block with the chat model and no tools."""
        return await summarize_with_model(request.app.state.settings.model, prompt)

    history_summary = await update_stored_summary(
        services.actions,
        conversation_id,
        request.app.state.settings.chat_summary_every,
        summarize,
    )

    adapter = VercelAIAdapter(agent=request.app.state.agent, run_input=run_input, accept=accept)

    async def on_complete(result) -> None:  # type: ignore[no-untyped-def]
        """Store the assistant text after a successful run."""
        output = getattr(result, "output", "")
        text = output if isinstance(output, str) else str(output)
        if text:
            services.actions.add_message(conversation_id, "assistant", text)

    async def encode() -> AsyncIterator[str]:
        """Run the agent while the MCP tools can see this conversation."""
        services_token = current_services.set(services)
        conversation_token = current_conversation_id.set(conversation_id)
        summary_token = current_history_summary.set(history_summary)
        jev_token = current_jev.set(screener_for(request.app.state.settings))
        try:
            event_stream = adapter.run_stream(on_complete=on_complete)
            async for chunk in adapter.encode_stream(event_stream):
                yield chunk
        finally:
            current_jev.reset(jev_token)
            current_history_summary.reset(summary_token)
            current_conversation_id.reset(conversation_token)
            current_services.reset(services_token)

    return StreamingResponse(
        encode(),
        media_type=accept,
        headers={"X-Conversation-Id": conversation_id},
    )
