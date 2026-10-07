# API tests

Python files here use the module docstring in `backend/AGENTS.md`. Every test function has a one-line docstring.

Run the suite with Docker Compose from Ubuntu, as described in `.cursor/rules/docker.mdc`. Tests use the in-memory invoice gateway in `fakes.py` and do not call Xero or a live model.

## Files

- `conftest.py` — signed-in API client fixture
- `fakes.py` — in-memory invoice gateway
- `test_auth.py` — shared login and session
- `test_actions.py` — payload validation and the confirm write boundary
- `test_conversations.py` — stored chat history
- `test_conversation_summary.py` — summary folding and history trim
- `test_guardrails.py` — redaction and the Jev input screen
- `test_observability.py` — trace redaction
- `test_mcp_tools.py` — the tool list has reads and `propose_action` only
- `test_mapping_and_summary.py` — Xero mapping and invoice totals
- `test_xero_oauth.py` — authorisation-code flow
- `test_evals.py` — golden dataset shape and offline evaluators
