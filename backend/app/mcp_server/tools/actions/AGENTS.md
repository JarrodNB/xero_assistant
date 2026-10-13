# Action tools

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`propose_action` inserts one pending action. It does not create, update, or void anything in Xero. The person confirms that row through the actions route.

Chat invoice updates accept original_line value selectors and removed_lines, never internal ids. Resolve selectors through actions/chat_updates.py before storage, but return only the original model-visible payload in tool events. This preparation may read Xero; it never writes.

Tool guidance must agree with the orchestrator: required details gate a proposal, while optional email, reference, and due date do not. Omitted due dates use the existing 14-day default. The confirmation card can still supply optional fields.

## Files

- `propose_action.py` — register `propose_action`
