# Xero client

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package talks to Xero. The browser never receives the client secret, refresh token, or access token. The HTTP client is not added to Langfuse instrumentation.

One stored refresh token and tenant serve every interviewer. Invoice and contact mapping belongs in `mapping.py`. Accounting writes are called by the invoice service, not by MCP tools.

## Files

- `oauth.py` — authorisation URL, scopes, and tenant choice
- `routes.py` — start and finish the authorisation-code flow
- `client.py` — token refresh and Accounting API calls
- `connection_store.py` — the one refresh token and tenant id
- `mapping.py` — Xero payloads to local contact and invoice records
