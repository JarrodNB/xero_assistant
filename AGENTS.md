# Ledger agent notes

Ledger is a Xero assistant for the demo company. The browser talks only to the Next.js app in `frontend`. The FastAPI service in `backend` owns sign-in, chat, invoices, and SQLite. Xero is the source of truth for contacts and invoices.

Run and test through Docker Compose, as described in `.cursor/rules/docker.mdc`.

Every folder has an `AGENTS.md`. Python file headers are defined in `backend/AGENTS.md`. TypeScript and TSX headers are defined in `frontend/AGENTS.md`.

## Layout

- `backend/` — API, chat agent, MCP tools, SQLite, Xero client, evals, and tests
- `frontend/` — Next.js UI, session calls, and the Xero OAuth proxy
- `.cursor/rules/` — repository engineering rules and the Docker workflow
- `README.md` — how to run the app
- `ARCHITECTURE.md` — request flow, the write boundary, and summarization

The model may call MCP read tools and `propose_action` only. A Xero write runs after a person confirms that proposal, or when they save or void an invoice in the UI.
