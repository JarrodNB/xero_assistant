# Action tools

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`propose_action` inserts one pending action. It does not create, update, or void anything in Xero. The person confirms that row through the actions route.

Tool guidance must agree with the orchestrator: required details gate a proposal, while optional email, reference, and due date do not. Omitted due dates use the existing 14-day default. The confirmation card can still supply optional fields.

## Files

- `propose_action.py` — register `propose_action`
