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
- `chat/` — orchestrator, invoices subagent, prompt, guardrails, summary, and chat routes
- `db/` — SQLite schema and repository
- `invoices/` — invoice records, the shared gateway, and invoice HTTP routes
- `mcp_server/` — in-process MCP tools the model may call
- `xero/` — OAuth and the Accounting API client
Phase 4 configuration validates AI deadlines, usage/output budgets, optional temperature, summary/history limits, fail-fast provider policy, and trace sampling at startup. Production supports `openai:` with SDK retries disabled. Application lifespan closes the owned OpenAI client and tracing provider alongside Xero/SQLite even if another cleanup fails.

Observability exports only AI metadata with pseudonymized conversation identifiers. Drop bodies, events, links, sensitive status text, and unrelated spans; sanitize finished-span copies and fail closed if sanitization fails. Root sampling defaults to 10%; external retention remains a deployment/account setting, documented as 30 days.
