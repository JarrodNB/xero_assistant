# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The orchestrator delegates contact and invoice reads to the invoices subagent and calls `propose_action` itself. The child does not propose. Personal data is replaced with numbered placeholders before the chat model, the summary model, and Jev. Tool arguments are restored for reads and `propose_action`. A delegated task stays tokenized. Tool results are protected again before a model reads them. API keys are redacted and are not restored. A known-phrase screen then refuses jailbreaks, physical harm, dosage questions, and clear self-harm statements. When `TYPESAFE_API_KEY` is set, Jev screens whatever that phrase screen allowed together with at most two protected preceding messages from the same conversation. Protected historical content has a combined 4,000-character budget allocated newest first. That context is request-scoped. Jev does not see the new assistant reply or the child brief.

Create proposals proceed when required details are known. Contact email, invoice reference, and invoice due date are independently optional. Mention them alongside a required clarification or the proposal without an optional-only question. Omitted invoice due dates retain the 14-day default; supplied values and resolved conversation context are preserved.

Before each parent or child model request, protect a copy of model history with the current turn's vault. A value learned from a tool result must use the same token in earlier prompt text on the next request. This keeps context-dependent personal-data detection from making an exact contact appear different. Stored originals and the confirmation write boundary remain in the trusted application.

## Packages

- `guardrails/` — protect personal data, redact secrets, refuse known phrases, then apply the strict input policy

## Files

- `orchestrator.py` — build the orchestrator, which delegates reads and calls `propose_action`
- `invoices_agent.py` — build the invoices subagent and its read tools
- `prompt.py` — orchestrator and invoices instructions, including the confirm-before-write rule
- `summary.py` — fold older messages into one stored summary of at most 2,000 characters
- `routes.py` — stream a turn and read saved conversations
