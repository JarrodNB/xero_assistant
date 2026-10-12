# SQLite

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

SQLite stores conversations, messages, the running chat summary, proposed actions, and the one Xero connection. The model does not query this database. MCP tools and routes call the repository.

Editor write receipts use `proposed_actions` with `ui-<request UUID>` ids and the message-free `ui-write-receipts` conversation. This thread is omitted from the chat list. Request ids bind to one action type and immutable validated payload. Claims and terminal transitions use conditional SQL updates, never a read followed by an unconditional write. Existing text status columns support the lifecycle without a schema migration.

## Files

- `schema.py` — tables and `create_engine_for`
- `repository.py` — conversations, messages, summaries, and proposed actions
