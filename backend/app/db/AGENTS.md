# SQLite

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

SQLite stores conversations, messages, the running chat summary, proposed actions, and the one Xero connection. The model does not query this database. MCP tools and routes call the repository.

## Files

- `schema.py` — tables and `create_engine_for`
- `repository.py` — conversations, messages, summaries, and proposed actions
