# Invoice tools

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

These tools read invoices and compute totals. They identify invoices by the number a person sees. Totals come from `app.invoices.summary`, not from a second copy of that math.

## Files

- `find_invoices.py` — list invoices by human-readable filters
- `get_invoice.py` — load one invoice by its number
- `summarize_invoices.py` — unpaid, overdue, and period totals
- `compare_invoice_totals.py` — compare two date ranges
