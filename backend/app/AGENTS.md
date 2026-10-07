# API package

Python files in this folder use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`main.py` builds the FastAPI app, session cookie, and routers. Domain behavior belongs in the packages below. A new module at this level is only for something shared by more than one package.

## Modules

- `main.py` — application factory
- `config.py` — environment settings
- `runtime.py` — request-scoped services and the current conversation id
- `errors.py` — `ApiError` for HTTP callers and `tool_error` for the model
- `observability.py` — Langfuse export with credential redaction

## Packages

- `actions/` — validate, store, and execute proposed writes
- `auth/` — the shared interviewer login
- `chat/` — agent, prompt, guardrails, summary, and chat routes
- `db/` — SQLite schema and repository
- `invoices/` — invoice records, the shared gateway, and invoice HTTP routes
- `mcp_server/` — in-process MCP tools the model may call
- `xero/` — OAuth and the Accounting API client
