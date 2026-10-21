"""Purpose: Tests for reading stored chat history.

Public API:
- test_conversation_history_lists_preview_and_detail
- test_unknown_conversation_is_not_found
- test_chat_reply_is_an_unbuffered_event_stream
- test_chat_jev_context_is_redacted_bounded_and_isolated
"""

import os
import time
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.chat.orchestrator import build_chat_agent
from app.mcp_server.server import build_mcp_server
from tests.conftest import USERNAME, sign_in


class _RecordingJev:
    """Pass each prompt while recording the exact protected text Jev would receive."""

    def __init__(self) -> None:
        """Start with no recorded prompts."""
        self.texts: list[str] = []

    async def guard(self, text: str, side: str) -> str:
        """Record one input-side screen and allow it."""
        assert side == "input"
        self.texts.append(text)
        return "pass"


def test_conversation_history_lists_preview_and_detail(api) -> None:
    """A signed-in client sees the newest preview, message order, and action payload."""
    client, _fake = api
    sign_in(client)
    repository = client.app.state.services.actions
    repository.ensure_conversation("empty")
    repository.ensure_conversation("older")
    repository.add_message("older", "user", "The user confirmed action abc. Done.")
    time.sleep(0.03)
    repository.add_message("older", "user", "Invoice Bob for 55 dollars please")
    time.sleep(0.03)
    repository.add_message("older", "assistant", "I can draft that.")
    stored = repository.create_action("older", "create_contact", {"name": "Bob"}, "Create contact Bob.")
    time.sleep(0.03)
    repository.ensure_conversation("newer")
    long_request = "List " + ("x" * 100)
    repository.add_message("newer", "user", long_request)

    listed = client.get("/conversations")
    assert listed.status_code == 200
    conversations = listed.json()["conversations"]
    assert [item["id"] for item in conversations] == ["newer", "older"]
    assert "empty" not in [item["id"] for item in conversations]
    newer = conversations[0]
    assert newer["preview"] == long_request[:80]
    assert newer["updated_at"]
    older = conversations[1]
    assert older["preview"] == "Invoice Bob for 55 dollars please"

    detail = client.get("/conversations/older")
    assert detail.status_code == 200
    payload = detail.json()
    assert [message["content"] for message in payload["messages"]] == [
        "The user confirmed action abc. Done.",
        "Invoice Bob for 55 dollars please",
        "I can draft that.",
    ]
    assert [message["role"] for message in payload["messages"]] == ["user", "user", "assistant"]
    assert payload["actions"][0]["action_id"] == stored.id
    assert payload["actions"][0]["kind"] == "proposed_action"
    assert payload["actions"][0]["action_type"] == "create_contact"
    assert payload["actions"][0]["status"] == "pending"
    assert payload["actions"][0]["summary"] == "Create contact Bob."
    assert payload["actions"][0]["payload"] == {"name": "Bob"}
    assert payload["actions"][0]["created_at"]


def test_unknown_conversation_is_not_found(api) -> None:
    """An unknown thread id returns 404."""
    client, _fake = api
    sign_in(client)
    missing = client.get("/conversations/missing")
    assert missing.status_code == 404
    assert missing.json()["what"] == "Conversation does not exist"


def test_chat_reply_is_an_unbuffered_event_stream(tmp_path: Path) -> None:
    """A browser fetch without an SSE Accept header still gets headers a proxy will not buffer."""
    from app.config import Settings
    from app.main import create_app
    from tests.fakes import FakeInvoiceGateway

    settings = Settings(
        app_username=USERNAME,
        app_password_hash=os.environ["APP_PASSWORD_HASH"],
        session_secret="test-session-secret",
        database_path=str(tmp_path / "app.db"),
        model="openai:gpt-4.1-mini",
    )
    agent = Agent(TestModel(custom_output_text="Hello there."))
    application = create_app(settings=settings, invoices=FakeInvoiceGateway(), agent=agent)
    body = {
        "id": "thread-1",
        "trigger": "submit-message",
        "messages": [{"id": "m1", "role": "user", "parts": [{"type": "text", "text": "Hi"}]}],
    }
    with TestClient(application) as client:
        sign_in(client)
        response = client.post(
            "/chat",
            json=body,
            headers={"Accept": "*/*", "X-Conversation-Id": "thread-1"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert '"type":"text-delta"' in response.text.replace(" ", "")
    assert "Hello" in response.text


def test_chat_jev_context_is_redacted_bounded_and_isolated(api, monkeypatch) -> None:
    """Each request exposes only its protected two-message tail to Jev."""
    client, _fake = api
    sign_in(client)
    repository = client.app.state.services.actions
    repository.ensure_conversation("thread-with-history")
    repository.add_message("thread-with-history", "user", "This oldest message must be dropped.")
    repository.add_message(
        "thread-with-history",
        "user",
        "Create an invoice for accounts@example.com for 1000000000000.",
    )
    repository.add_message(
        "thread-with-history",
        "assistant",
        "The maximum amount is 999999999999.99.",
    )
    recorder = _RecordingJev()
    monkeypatch.setattr("app.chat.routes.screener_for", lambda _settings: recorder)

    def respond(_messages, _info):  # type: ignore[no-untyped-def]
        """Return a deterministic response after the guardrail passes."""
        return ModelResponse(parts=[TextPart(content="Okay.")])

    client.app.state.agent = build_chat_agent(FunctionModel(respond), build_mcp_server())

    first = client.post(
        "/chat",
        json=_chat_body("Use the maximum amount you just said."),
        headers={"X-Conversation-Id": "thread-with-history"},
    )
    second = client.post(
        "/chat",
        json=_chat_body("How much is unpaid?"),
        headers={"X-Conversation-Id": "separate-thread"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(recorder.texts) == 2
    contextual = recorder.texts[0]
    assert "This oldest message must be dropped." not in contextual
    assert "accounts@example.com" not in contextual
    assert "[redacted_email:1]" in contextual
    assert "999999999999.99" not in contextual
    assert "assistant: The maximum amount is [redacted_bank_account:" in contextual
    assert contextual.endswith("Latest user message:\nUse the maximum amount you just said.")
    assert recorder.texts[1] == "How much is unpaid?"


def _chat_body(prompt: str) -> dict[str, object]:
    """Build one minimal Vercel AI chat request."""
    return {
        "id": "message-1",
        "trigger": "submit-message",
        "messages": [{"id": "message-1", "role": "user", "parts": [{"type": "text", "text": prompt}]}],
    }
