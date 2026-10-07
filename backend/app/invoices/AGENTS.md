# Invoices and contacts

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

Contact and invoice reads and writes go through `InvoiceGateway`. The chat confirm route and the invoice editor both use that gateway. Summary math stays pure and does not call Xero.

## Files

- `records.py` — contact, invoice, and line-item values shared by Xero, tools, and the UI
- `gateway.py` — the operation interface and its not-found errors
- `xero_service.py` — that interface against the connected demo company
- `summary.py` — unpaid, overdue, and period totals
- `routes.py` — invoice list, editor, and contact list HTTP routes
