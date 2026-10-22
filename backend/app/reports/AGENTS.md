# Performance reports

Read-only financial reports use the existing Xero client. This module owns typed report inputs/results, validation and source evidence. HTTP and future MCP callers share the same interface; never derive P&L or balance-sheet amounts from invoices. Use Decimal for arithmetic and decimal strings in outputs. Raw reports are request-local and never logged or sent to providers.

All Python files use the header and function-docstring conventions in backend/AGENTS.md.

## Files
- `routes.py` — authenticated report HTTP interface.
- `models.py` — versioned decimal-string report and source-row contracts; account identities are excluded from serialization.
- `normalization.py` — bounded standard English layout validation and evidence extraction.
- `service.py` — organisation currency/timezone validation, report reads and whole-operation timeout.
- `comparison.py` — exact account alignment, supported P&L semantics, source reconciliation, ranked contributors and remainder.
- `periods.py` — organisation-local completed-month, previous-period/year and explicit custom range resolution.

Comparison reads metadata once plus two reports under a single deadline. Never zero-fill an empty/unsupported source. Validate every source's totals before ID alignment; reject ambiguous identity or changing income/expense classification. Use a 50-digit local Decimal context, meaningful percentage baselines, report-prefixed source keys and top-five contributions plus a reconciling remainder. Internal account IDs remain excluded from serialization; public movement indexes are request-local, not stable account selectors for future refreshed chat reads.

Single P&L uses two bounded GETs (organisation and report) under one configured deadline. Reports are feature-flagged off by default. Missing report permission is distinct from an existing Xero connection; never infer report consent from connection status. Use the documented Windows-to-IANA timezone map and explicit currency precision policy; unsupported values fail honestly.
