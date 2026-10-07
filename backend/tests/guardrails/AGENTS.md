# Guardrail tests

Python files here use the module docstring in `backend/AGENTS.md`. Every test function has a one-line docstring.

These tests script the model and do not call Jev or Xero. The known-phrase cases live in the test module. A chat request runs the same screen.

## Files

- `test_phrase_screen.py` — known-phrase refusals, allowed invoice messages, and the chain with Jev
