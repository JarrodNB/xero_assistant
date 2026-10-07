# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The orchestrator delegates contact and invoice reads to the invoices subagent and calls `propose_action` itself. The child does not propose. Secrets are redacted before the chat model, the summary model, and tool results. When `TYPESAFE_API_KEY` is set, Jev screens the user message on the orchestrator and does not see the assistant reply or the child brief.

## Files

- `orchestrator.py` — build the orchestrator, which delegates reads and calls `propose_action`
- `invoices_agent.py` — build the invoices subagent and its read tools
- `prompt.py` — orchestrator and invoices instructions, including the confirm-before-write rule
- `guardrails.py` — secret redaction and the Jev input screen
- `jev.py` — Jev client, thresholds, and refusal routes. The user-message cases live in `backend/evals/jev/user_message/`.
- `summary.py` — fold older messages into the stored summary
- `routes.py` — stream a turn and read saved conversations
