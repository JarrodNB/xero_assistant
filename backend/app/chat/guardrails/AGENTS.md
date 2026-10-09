# Chat guardrails

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`__init__.py` only composes the input chain and the tool-result guard. Secret redaction lives in `redaction.py`. The strict input policy, its thresholds, and the user-message screen live in `policy_screen.py`. That screen currently calls Jev. Known phrases run before it. It does not see the assistant reply or the child brief. The user-message cases live in `backend/evals/jev/user_message/`.

## Files

- `__init__.py` — wire redaction, the known-phrase screen, and the policy screen into `chat_guardrails`
- `redaction.py` — secret, card, SSN, and IBAN redaction for prompts, summaries, and tool results
- `phrase_screen.py` — known jailbreak, harm, dosage, and self-harm phrases
- `policy_screen.py` — strict input policy, refusal routes, and the user-message screen
