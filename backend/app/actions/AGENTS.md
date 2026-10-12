# Proposed actions

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package is the chat write boundary. `propose_action` only stores a pending row. `routes.py` confirm is the chat path that writes to Xero, after merging optional fields the person supplied on the card.

Confirmation freezes its payload while atomically changing `pending` to `executing`. Denial only changes `pending` to `denied`. Final results are conditional transitions from `executing`; never reset `unknown` or stale claims to `pending`. Repeated confirmation returns an existing result/status without another gateway call. Use the service for editor writes too.

Update lines use `UpdateLineItemPayload`: only editable values plus an invoice-scoped UUID are accepted. Accounting fields come from fresh Xero data. `removed_line_item_ids` makes removals explicit. Missing or null update references leave the existing reference unchanged; an empty string clears it. Omitted/null due dates leave the date unchanged; due-date clearing is not supported in this editor.

## Files

- `service.py` — atomic claims, bounded execution, durable result replay, and quarantine of uncertain chat/editor writes

- `payloads.py` — validate create, update, and void payloads before they are stored or executed
- `executor.py` — run one confirmed action through the invoice gateway
- `routes.py` — confirm or deny a pending action
