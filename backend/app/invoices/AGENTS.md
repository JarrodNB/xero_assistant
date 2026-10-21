# Invoices and contacts

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

Contact and invoice reads and writes go through `InvoiceGateway`. The chat confirm route and the invoice editor both use that gateway. Summary math stays pure and does not call Xero.

Editor mutations use the shared actions service and durable write receipts. Accept `X-Write-Id` as a UUID, reject reuse for a different operation/payload, and return the original success on repetition. Without a supplied id, the server treats the call as a new intentional write. Unknown or abandoned outcomes are quarantined; verify Xero before a new write.

## Files

- `line_updates.py` — invoice-scoped line identity validation and preservation of server-owned accounting fields

- `records.py` — contact, invoice, and line-item values shared by Xero, tools, and the UI
- `gateway.py` — the operation interface and its not-found errors
- `xero_service.py` — that interface against the connected demo company
- `summary.py` — unpaid, overdue, and period totals
- `routes.py` — invoice list, editor, and contact list HTTP routes

Metadata-only updates must omit `LineItems`. Line replacements retain every existing id or explicitly name its removal; unidentified or foreign lines cannot silently replace existing accounting data. Use defaults only for new lines and preserve the original amount convention. Reject unsupported raw fields, ambiguous discounts, and amount changes on lines exposing `TaxAmount` before writing. Editor HTTP serialization includes identities/capabilities; ordinary model tool results do not.

Phase 5 reads return InvoiceReadResult with pre-filter completeness, scanned row count, and cap. Retain 20 pages plus one non-retained lookahead; require complete reads before aggregation. Resolve bounded contact searches and apply ContactIDs, sales type, status and dates upstream. Never treat a malformed page as empty. Keep currency grouping and date-order validation in the pure summary module. schemas.py defines typed v2 HTTP and MCP outputs; do not reintroduce scalar cross-currency totals. Empty currency arrays have no assumed currency. Concurrent Xero reads are not a transactional snapshot.
