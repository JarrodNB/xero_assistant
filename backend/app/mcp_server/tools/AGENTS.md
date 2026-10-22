# MCP tool domains

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`__init__.py` re-exports each tool registrar. Add a tool as its own module inside the domain package, then export its registrar from that package and from this file.

## Packages

- `contacts/` — contact reads
- `invoices/` — invoice reads and totals
- `actions/` — store a pending write for a person to confirm

- `reports/` — one registrar per report tool, plus protected evidence/value-free handoff schemas; no raw report or monetary payloads to unconstrained chat.
