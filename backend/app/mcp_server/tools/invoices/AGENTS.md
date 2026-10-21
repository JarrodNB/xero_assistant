# Invoice tools

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

These tools read invoices and compute totals. They identify invoices by the number a person sees. Totals come from `app.invoices.summary`, not from a second copy of that math.

## Files

- `find_invoices.py` — list invoices by human-readable filters
- `get_invoice.py` — load one invoice by its number
- `summarize_invoices.py` — unpaid, overdue, and period totals
- `compare_invoice_totals.py` — compare two date ranges

Financial read tools expose typed v2 success/error unions (FastMCP structured result envelope). Lists propagate complete/scanned_count/limit/next_step; partial empty lists cannot establish absence. Summary/comparison failures expose no amounts when the bounded read is incomplete. Explain separate native currency groups, empty groups, and zero-filled period alignment in descriptions. Preserve versioned output schemas and shared pure totals.
