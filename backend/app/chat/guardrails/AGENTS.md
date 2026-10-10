# Chat guardrails

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`__init__.py` only composes the input chain and the tool guard. Presidio placeholders live in `pii.py`. `redaction.py` applies that vault to prompts and tool calls, and still strips API keys. `context.py` protects and formats the latest prompt with at most two protected preceding user or assistant messages from the same request. Historical content has a combined 4,000-character budget, allocated newest message first, then the beginning of the older message up to the remainder. The formatter tells Jev to classify the latest message, use history only to resolve references, and treat adoption or continuation of a historical hazard as hazardous. The strict input policy, its thresholds, and the user-message screen live in `policy_screen.py`. That screen currently calls Jev. Known phrases run before it. It does not see the new assistant reply or the child brief. The user-message cases live in `backend/evals/jev/user_message/`.

## Files

- `__init__.py` — wire protection, secret redaction, the known-phrase screen, and the policy screen into `chat_guardrails`
- `context.py` — protect, type, bound, and format request-scoped conversation context for Jev
- `pii.py` — Presidio vault, numbered placeholders, and restoring the outbound stream. A person hit that is only an invoice field label, such as a reference, is left as written.
- `redaction.py` — protect prompts and tool results, restore tool arguments, and strip secrets
- `phrase_screen.py` — known jailbreak, harm, dosage, and self-harm phrases
- `policy_screen.py` — strict input policy, refusal routes, and the user-message screen
