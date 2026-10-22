# Performance reports

Read-only financial reports use the existing Xero client. This module owns typed report inputs/results, validation and source evidence. HTTP and future MCP callers share the same interface; never derive P&L or balance-sheet amounts from invoices. Use Decimal for arithmetic and decimal strings in outputs. Raw reports are request-local and never logged or sent to providers.

All Python files use the header and function-docstring conventions in backend/AGENTS.md.

## Files
- `routes.py` — authenticated report HTTP interface.
- `models.py` — versioned decimal-string report and source-row contracts; account identities are excluded from serialization.
- `normalization.py` — bounded standard English layout validation and evidence extraction.
- `service.py` — organisation currency/timezone validation, report reads and whole-operation timeout.
- `comparison.py` — exact account alignment, supported P&L semantics, source reconciliation, ranked contributors and remainder; its single-source validator also gates standalone P&L responses.
- `periods.py` — organisation-local completed-month, previous-period/year and explicit custom range resolution.
- `balance_sheet.py` — as-of presets, supported position sections, subtotal/accounting-identity validation and category-preserving deltas.
- `amounts.py` — shared exact monetary comparisons and meaningful percentage policy.

BalanceSheetQuery and the P&L query models reject extra parameters. Position reports use as_of rather than date_from/date_to and request periods=0; never infer a column's date. Validate assets, liabilities, equity and net-assets totals against classified account leaves and the accounting identity. Preserve negative/contra accounts; reject duplicate identities, category changes, missing totals and unverified sections. PositionMovement has no contribution field. Known global total Row forms without account IDs can be normalized as summaries; do not match account labels as identities.

Comparison reads metadata once plus two reports under a single deadline. Never zero-fill an empty/unsupported source. Validate every source's totals before ID alignment; reject ambiguous identity or changing income/expense classification. Use a 50-digit local Decimal context, meaningful percentage baselines, report-prefixed source keys and top-five contributions plus a reconciling remainder. Internal account IDs remain excluded from serialization; public movement indexes are request-local, not stable account selectors for future refreshed chat reads.

Single P&L uses two bounded GETs (organisation and report) under one configured deadline. Reports are feature-flagged off by default. Missing report permission is distinct from an existing Xero connection; never infer report consent from connection status. Use the documented Windows-to-IANA timezone map and explicit currency precision policy; unsupported values fail honestly.

- `context.py` — expiring signed public dates/nonce plus opaque tenant/account HMACs; refetch and unique identity matching; no encoded private IDs or retained snapshots. Comparison results include optional explanation_context selectors and have a configured post-decoration byte limit.

The app owns one ReportService so HTTP and chat share the per-process rolling rate limit. `_operation` pins trusted tenant identity across metadata and report GETs and rejects reconnects. Do not construct a fresh service per request or use movement-N/position-N as refreshed identity. `/explanation-source` revalidates the token and refetches both reports before returning the newly matched public key. Deleted/ambiguous/tampered/expired/cross-tenant context fails closed.

An empty comparison does not relax source validation. Validate every populated source before returning or disclosing its rows, even when the other source is empty. Shared single-source validation preserves the same precision and reconciliation policy in standalone and comparison paths.
