# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The orchestrator delegates contact and invoice reads to the invoices subagent and calls `propose_action` itself. The child does not propose. Personal data is replaced with numbered placeholders before the chat model, the summary model, and Jev. Tool arguments are restored for reads and `propose_action`. A delegated task stays tokenized. Tool results are protected again before a model reads them. API keys are redacted and are not restored. A known-phrase screen then refuses jailbreaks, physical harm, dosage questions, and clear self-harm statements. When `TYPESAFE_API_KEY` is set, Jev screens whatever that phrase screen allowed together with at most two protected preceding messages from the same conversation. That context is request-scoped. Jev does not see the new assistant reply or the child brief.

## Packages

- `guardrails/` — protect personal data, redact secrets, refuse known phrases, then apply the strict input policy

## Files

- `orchestrator.py` — build the orchestrator, which delegates reads and calls `propose_action`
- `invoices_agent.py` — build the invoices subagent and its read tools
- `prompt.py` — orchestrator and invoices instructions, including the confirm-before-write rule
- `summary.py` — fold older messages into one stored summary of at most 2,000 characters
- `routes.py` — stream a turn and read saved conversations
