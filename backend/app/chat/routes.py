"""Purpose: Stream a chat turn and keep the conversation id available to propose_action.

Public API:
- router
- latest_user_text
"""

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError

from app.auth.routes import require_user
from app.runtime import current_conversation_id, current_services
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.vercel_ai import VercelAIAdapter

router = APIRouter(tags=["chat"])


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
        try:
            event_stream = adapter.run_stream(on_complete=on_complete)
            async for chunk in adapter.encode_stream(event_stream):
                yield chunk
        finally:
            current_conversation_id.reset(conversation_token)
            current_services.reset(services_token)

    return StreamingResponse(
        encode(),
        media_type=accept,
        headers={"X-Conversation-Id": conversation_id},
    )
