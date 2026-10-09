# Chat guardrails

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`__init__.py` only composes the input chain and the tool guard. Presidio placeholders live in `pii.py`. `redaction.py` applies that vault to prompts and tool calls, and still strips API keys. The strict input policy, its thresholds, and the user-message screen live in `policy_screen.py`. That screen currently calls Jev. Known phrases run before it. It does not see the assistant reply or the child brief. The user-message cases live in `backend/evals/jev/user_message/`.

## Files

- `__init__.py` — wire protection, secret redaction, the known-phrase screen, and the policy screen into `chat_guardrails`
- `pii.py` — Presidio vault, numbered placeholders, and restoring the outbound stream. A person hit that is only an invoice field label, such as a reference, is left as written.
- `redaction.py` — protect prompts and tool results, restore tool arguments, and strip secrets
- `phrase_screen.py` — known jailbreak, harm, dosage, and self-harm phrases
- `policy_screen.py` — strict input policy, refusal routes, and the user-message screen
