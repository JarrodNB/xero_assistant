# Proposed actions

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package is the chat write boundary. `propose_action` only stores a pending row. `routes.py` confirm is the chat path that writes to Xero, after merging optional fields the person supplied on the card.

## Files

- `payloads.py` — validate create, update, and void payloads before they are stored or executed
- `executor.py` — run one confirmed action through the invoice gateway
- `routes.py` — confirm or deny a pending action
