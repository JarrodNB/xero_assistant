# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The agent may call MCP read tools and `propose_action` only. Secrets are redacted before the chat model, the summary model, and tool results. When `TYPESAFE_API_KEY` is set, Jev screens the user message and does not see the assistant reply.

## Files

- `agent.py` — build the PydanticAI agent and its MCP toolset
- `prompt.py` — system instructions, including the confirm-before-write rule
- `guardrails.py` — secret redaction and the Jev input screen
- `jev.py` — Jev client, thresholds, and refusal routes
- `summary.py` — fold older messages into the stored summary
- `routes.py` — stream a turn and read saved conversations
