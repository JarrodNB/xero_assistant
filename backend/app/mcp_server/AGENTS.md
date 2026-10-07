# MCP server

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`server.py` registers one tool module per domain. The exposed tools are `find_contacts`, `find_invoices`, `get_invoice`, `summarize_invoices`, `compare_invoice_totals`, and `propose_action`. Do not register a tool that writes to Xero.

Tool descriptions say when to use the tool, when not to, the parameters, and one or two short examples. Tool errors tell the model what failed, whether to retry, and what to do next, without internal database ids.

## Files

- `server.py` — build the in-process FastMCP server
- `context.py` — current-turn services and date parsing for tools
- `tools/` — one module per tool, grouped by domain
