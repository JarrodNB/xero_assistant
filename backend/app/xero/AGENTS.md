# Xero client

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package talks to Xero. The browser never receives the client secret, refresh token, or access token. The HTTP client is not added to Langfuse instrumentation.

One stored refresh token and tenant serve every interviewer. Invoice and contact mapping belongs in `mapping.py`. Accounting writes are called by the invoice service, not by MCP tools.

Accounting writes carry one idempotency key across bounded identical HTTP retries. A confirmed action derives that key from its durable receipt id. Xero keys expire after six minutes: never replay a completed or uncertain receipt as a new external request. OAuth grants are not automatically retried. Serialize refresh-token rotation, sanitize provider/network errors, and distinguish unknown write outcomes from definite rejection.

Mapping retains line identities and edit capability flags for the HTTP editor. Raw account, tax, tracking, item, and discount values remain server-owned and are fetched again before line changes. Never infer tax-override intent from the presence of `TaxAmount` or silently change a line's account/tax to the create defaults.

## Files

- `oauth.py` — authorisation URL, scopes, and tenant choice
- `routes.py` — start and finish the authorisation-code flow
- `client.py` — token refresh and Accounting API calls
- `client.py` also exposes `get_bounded` for reporting: decoded response bytes are capped before JSON parsing and streams close on rejection. Existing invoice/contact reads keep their current interface.
- `connection_store.py` — the one refresh token and tenant id
- `mapping.py` — Xero payloads to local contact and invoice records
