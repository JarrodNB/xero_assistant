"""Purpose: Tests for reading stored chat history.

Public API:
- test_conversation_history_lists_preview_and_detail
- test_unknown_conversation_is_not_found
"""

import time

from tests.conftest import sign_in


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
