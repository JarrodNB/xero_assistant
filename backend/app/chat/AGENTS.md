# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The orchestrator delegates contact and invoice reads to the invoices subagent and calls `propose_action` itself. The child does not propose. Secrets are redacted before the chat model, the summary model, and tool results. A known-phrase screen then refuses jailbreaks, physical harm, dosage questions, and clear self-harm statements. When `TYPESAFE_API_KEY` is set, Jev screens whatever that phrase screen allowed. Jev does not see the assistant reply or the child brief.

## Packages

- `guardrails/` — redact secrets, refuse known phrases, then apply the strict input policy

## Files

- `orchestrator.py` — build the orchestrator, which delegates reads and calls `propose_action`
- `invoices_agent.py` — build the invoices subagent and its read tools
- `prompt.py` — orchestrator and invoices instructions, including the confirm-before-write rule
- `summary.py` — fold older messages into one stored summary of at most 2,000 characters
- `routes.py` — stream a turn and read saved conversations
