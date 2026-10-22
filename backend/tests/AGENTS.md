# API tests

Python files here use the module docstring in `backend/AGENTS.md`. Every test function has a one-line docstring.

Run the suite with Docker Compose from Ubuntu, as described in `.cursor/rules/docker.mdc`. Tests use the in-memory invoice gateway in `fakes.py` and do not call Xero. Harness tests script the model. The golden and judge evals call the configured chat model. The Jev user-message dataset calls the configured Jev model.

## Files

- `test_reports.py` — report authentication, permission/rollout states, exact source rows, unsupported layouts/currencies/timezones, decoded-byte and row caps, cancellation, and default period resolution.
- `test_report_comparisons.py` — authenticated P&L comparison, ID alignment/renames/credits, top-five remainder, source reconciliation and high-precision cancellation, calendar/custom periods, invalid-range and empty-source semantics.
- `test_balance_sheets.py` — typed as-of reads, nested/flat standard sections, negative assets, global/local totals and identity validation, missing/new/reclassified accounts, empty data, authentication/flagging and date presets.

- `test_invoice_edits.py` also covers id-free MCP proposals, deterministic original-value matching, ambiguous/stale selectors, explicit removals/additions, and confirmation against the Xero service. `test_guardrails.py` verifies private ids are removed only from provider-history copies.

- `test_write_safety.py` — concurrent claims, denial races, cancellation, deadlines, restart recovery, editor receipt reuse, and Xero retry/error behavior
- `test_invoice_edits.py` — partial writes, explicit removals, accounting metadata preservation, unsafe-edit rejection, and reference clearing

- `conftest.py` — signed-in API client fixture
- `fakes.py` — in-memory invoice gateway
- `test_auth.py` — shared login and session
- `test_actions.py` — payload validation and the confirm write boundary
- `test_conversations.py` — stored chat history and request-scoped Jev context
- `test_conversation_summary.py` — summary folding and history trim
- `test_guardrails.py` — redaction, Jev context message/character bounds, and the Jev input screen
- `test_observability.py` — trace redaction
- `test_mcp_tools.py` — the tool list has reads and `propose_action` only
- `test_mapping_and_summary.py` — Xero mapping and invoice totals
- `test_xero_oauth.py` — authorisation-code flow
- `test_agents.py` — orchestrator delegation and the invoices tool boundary
- `test_evals.py` — deterministic dataset scores, judge dataset scores, and the Jev user-message score

## Packages

- `guardrails/` — known-phrase screen cases

## Evaluation workflow (Phase 3)

Ordinary `pytest -q` runs offline tests and skips `live_eval` cases. Paid tests require `pytest -q --live-evals -m live_eval`; runner CLIs require `--live`, default to deterministic scoring, and support repeated `--case NAME` selections. Agent runners also support `--scoring judge`. Run through Docker Compose in Ubuntu. No production chat request runs these datasets.

Every selected case must appear exactly once with nonempty all-true assertions. Task failures and evaluator exceptions are separate failure channels and both must fail the run. Judge approval never bypasses deterministic write-claim or proposal checks. Shared validation and safe artifact handling live in `evals/reporting.py`; offline regression coverage is in `tests/test_eval_reporting.py`.

Use one deterministic case first. Concurrency is two, task deadline 90 seconds, dataset deadline 900 seconds including judging, and agent task usage is capped at 12 requests, 12 tools, and 20,000 tokens per case. Judge/Jev usage is not in that token cap; review provider billing before broad runs. Judge models use configured `MODEL`. Model aliases remain mutable; configure snapshots for comparable results.

Artifacts under `evals/artifacts/` are local and git-ignored. Retain only allowlisted metadata (versions/hashes, model identifiers, task usage, assertion booleans, latency); never persist prompts, answers, reasons, or exception bodies. Billing cost and judge/Jev usage are explicitly unavailable. Delete artifacts after 30 days; publish only reviewed summaries.
- `test_ai_execution.py` — authoritative parent/child limits, safe streaming failures, deadlines at preparation/provider/tool boundaries, summary fallback, provider policy, and cancellation isolation.
- `test_observability.py` also verifies actual SDK finished-span sanitization. Tests clear tracing credentials to prevent remote exports.

- test_financial_completeness.py covers currency grouping, period alignment, empty/missing currency, reversed dates, cap/lookahead boundaries, upstream filtering, malformed pages, contact truncation, typed HTTP/MCP schemas, and deterministic answer checks. No providers or live Xero are used.

- `test_report_chat.py` — signed identity/refetch/source evidence, tenant reconnect, report-only FunctionModel/MCP output, PII/injection/provider/guard fallback, request/tool/token/character/deadline/rate/result limits and ordinary-history isolation. No live providers/Xero.
- `test_report_evals.py` — report golden CI and separate opt-in judge guards, including exact seven-account displayed-contributor reconciliation.
