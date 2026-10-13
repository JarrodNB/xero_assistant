# Next demo feature: explain a profit change

Discovery for XERO-5, 13 October 2026. This document recommends future work; no feature, OAuth change, live-company check, or evaluation has been implemented or run.

## Decision

Build a **read-only profit-and-loss variance briefing**: compare two completed calendar months, show the largest reported account movements, and explain their arithmetic contribution to the profit change with visible source rows. The demo question is “What changed in profit between these two months, and where should I look first?”

This moves Ledger from finding and editing transactions to explaining business performance. It is distinct from the existing invoice-total comparison: a P&L includes reported income and costs; summing authorised/paid sales invoices is neither a full profit measure nor proof of cash collected. The assistant must explain observed movements, never invent their business causes or present an accounting diagnosis.

The recommendation is conditional on a future Demo Company preflight confirming report access, a supported report layout, and two useful periods. If that fails, revisit this decision before implementing; do not silently substitute invoice totals or manufacture live data.

## Alternatives

Scores are discovery judgments, not measured results. Five is best; feasibility includes implementation effort, and reliability includes data and authorization dependencies. Distinctness and impact matter most for this ticket.

| Concept | Demo impact | Distinctness | Feasibility | Reliability | Assessment |
| --- | --- | --- | --- | --- | --- |
| P&L variance briefing | 5 | 5 | 3 | 3 | Recommended: clear business question, evidence-backed explanation, bounded read-only scope. Report parsing and new consent need preflight. |
| Prioritized overdue collection worklist | 4 | 3 | 4 | 4 | Useful and largely supported by invoice fields, but the current assistant already answers unpaid/overdue questions. Drafting messages could add value later; sending requires a separate approved integration. |
| Short-term cash forecast | 5 | 5 | 2 | 2 | Compelling, but invoices alone omit cash balances, payments, costs, and timing assumptions. A reliable forecast adds substantial integration and uncertainty work. |
| Duplicate invoice/anomaly review | 3 | 4 | 3 | 3 | A different read-only workflow, but needs representative duplicates and carefully evaluated heuristics; sparse demo data may make it unconvincing. |
| Bills CRUD | 2 | 1 | 3 | 4 | Repeats the existing transaction editing story. Excluded by ticket direction. |

P&L wins because it answers a visibly different question without adding write execution, email delivery, forecasting models, or infrastructure. Collections is the strongest alternative if report access/data makes P&L impractical, rather than an extra MVP deliverable.

## Current code evidence

Paths below are relative to this document. These are extension points and constraints, not new implementation claims.

- [README](../../README.md) describes contacts, invoice reads, period comparisons, confirmation cards, and invoice editing. [Architecture](../../ARCHITECTURE.md) establishes Next.js → FastAPI → Xero, MCP reads, bounded agent execution, and the human write boundary.
- [Invoice summary](../../backend/app/invoices/summary.py), `compare_invoice_periods` and `_recognised_total`, uses invoice issue dates and AUTHORISED/PAID totals. `summarize_invoice_records` calculates overdue amounts, but its summary has no currency grouping. Neither function reads accounting reports.
- [Invoice service](../../backend/app/invoices/xero_service.py), `_fetch_invoices`, pages through at most 20 batches and returns a list without completeness metadata. `_where_clause` filters status and issue dates, without enforcing ACCREC. A collections implementation would need explicit sales filtering, currency groups, and completeness reporting; it cannot assume this reader is a ready-made receivables ledger.
- [Invoice records](../../backend/app/invoices/records.py) and [Xero mapping](../../backend/app/xero/mapping.py) retain due dates, outstanding amounts, and invoice currency, useful for the collections alternative. They do not model report rows or report basis. Existing JSON money serialization uses floats; the proposed report contract should use decimal strings.
- [OAuth](../../backend/app/xero/oauth.py), `SCOPES`, requests invoices, contacts, and settings, but no report scope. `choose_tenant` prefers a demo name and otherwise chooses the first connection: a future demo preflight must verify the selected organization rather than rely on that fallback.
- [Xero client](../../backend/app/xero/client.py) already provides server-owned authenticated GETs and bounded retries. [Invoices agent](../../backend/app/chat/invoices_agent.py), `INVOICE_READ_TOOLS`, allowlists five contact/invoice tools. Reporting needs its own explicitly allowed tool and prompt routing; the current child does not have that capability.

## Official API feasibility

References checked on 13 October 2026; public documentation only, without tenant access.

- [Xero Reports documentation](https://developer.xero.com/documentation/api/accounting/reports) and [Xero's Accounting OpenAPI specification](https://github.com/XeroAPI/Xero-OpenAPI/blob/master/xero_accounting.yaml) establish the P&L read endpoint. The specification describes date ranges, comparative periods, standard layout, cash-basis selection, and structured report rows. Prefer two explicit date-range reads with standard layout and accrual basis for this MVP; verify returned headers rather than infer column dates. It avoids dependence on comparative-column ordering. The specification still lists the older report scope, so use the current scope guidance below for authorization.
- [OAuth scopes](https://developer.xero.com/documentation/guides/oauth2/scopes/), [Xero's granular-scope mapping](https://github.com/XeroAPI/xero-prompt-library/blob/main/python/SKILL.md), and [API changelog](https://developer.xero.com/changelog) support requesting `accounting.reports.profitandloss.read`. The March 2026 scope changes replaced broad report access; legacy broad scopes expire in September 2027. Existing Ledger consent does not grant the needed report access; changing requested scopes requires reconnecting. Validate app eligibility and user report permissions in preflight. Do not add unrelated report or journal access.
- [Invoice API](https://developer.xero.com/documentation/api/accounting/invoices) documents due dates and remaining balances in invoice currency, supporting the collections alternative but not a complete cash forecast.
- [Rate-limit guidance](https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/) makes bounded requests and deliberate handling of throttling necessary. No polling, per-account report requests, or scheduled refresh belongs in this MVP. Recheck applicable platform quotas before implementation; the proposed limits below are application budgets, not claims about Xero's quotas.

## MVP and exclusions

Accept two explicit, distinct completed calendar months. Default relative requests to the previous two completed months using a documented organization/demo timezone; display the resolved dates before analysis. Reject invalid, future, or mismatched periods. Support the verified Demo Company standard accrual layout and organization base currency only.

Return revenue, expense, and net-profit totals for both periods, absolute changes, and at most five account movements ordered by absolute signed contribution to profit change. Retain an “other movements” remainder and reconcile it with the report's profit delta within the currency's rounding tolerance. Do not double count summary rows and their underlying accounts. Match accounts using trusted identifiers when supplied; fail unsupported/ambiguous alignment rather than match by a guessed label. Percent changes are omitted with an explanation when the baseline is zero or negative.

Show a comparison card with source period, basis, currency, retrieval time, and expandable evidence rows. A chat answer may say “Reported rent rose by X and contributed Y to the profit movement”; it cannot say why rent rose unless the user supplies verified evidence. Follow-up “show the biggest expense change” uses the same bounded comparison context or refreshes explicitly. Offer to inspect the source in Xero; transaction drilldown is outside the MVP.

Exclude bills, writes, emailed reports/reminders, bank reconciliation, transaction causality, forecasting, budgets, tracking-category comparisons, custom/localized report layouts, multiple organizations, exports, recurring jobs, vector retrieval, and new hosting services. No ledger replication or migration is required. Broader layout/currency support is a later decision.

## Proposed architecture and safety

Keep the browser calling Next.js only. FastAPI owns an isolated typed report adapter and deterministic variance calculator using the existing Xero client. Register a versioned MCP tool such as `compare_profit_and_loss` with typed month inputs and explicit usage guidance. Route report questions directly from the orchestrator to this read tool; do not expand the invoices child's responsibility. Implementation must keep source-purpose headers, function descriptions, and folder AGENTS current.

The proposed tool result includes schema version, resolved periods, basis, currency, retrieval time, supported/complete status, decimal-string totals, evidence row keys, ranked movements, remainder, and warnings. Backend identifiers stay private; model evidence keys are opaque request-local aliases. Cap each source report at 500 leaf rows and 1 MiB decoded response; reject oversized or incomplete reports rather than describe them as complete. Bound the protected model result to 12,000 characters, including the top five rows and totals; say explicitly that other details are omitted while calculations used the complete validated reports. Validate totals, finite decimals, report type, period headers, and row alignment before model use.

Use Python/PydanticAI and a Pydantic narrative result containing a short summary, evidence-key references, and limitations. Reject unknown evidence keys or unsupported numerical claims; allow at most the existing configured validation retry within the shared budget, then show the deterministic card alone. Put prompt text in a versioned template, provisionally `profit-variance-v1`, with injected values separate. Reuse configuration and explicitly pin a tested model snapshot before promotion; do not assume current mutable model aliases provide reproducibility.

Report labels and tool output are untrusted. Apply the centralized redaction vault, deterministic injection detection, and configured Jev screening to the minimum relevant context; a guardrail failure prevents model narration. Send protected account labels, aggregates, and selected evidence only, excluding organization names, bank details, raw report bodies, transaction descriptions, and internal IDs. Do not assume account labels contain no personal data. Restore tokens only in the trusted app. Confirm provider retention/training terms before enabling the use case; keep token mappings request-scoped in the existing vault.

Retain explicit dates/basis and evidence aliases in bounded turn context. Do not persist a raw report snapshot or put report contents in summaries/traces. Follow-ups after context loss must request dates or refetch; they must not guess earlier values. First-turn prompt-cache checking follows the existing policy where applicable; any cache must be tenant-scoped and must not reuse private report data across sessions. No new caching service is needed.

Apply the existing 60-second turn deadline, shared 12-request/12-tool/20,000-token limits, 20-second model timeout, and 2,048-output-token cap. Limit this report operation to two report GETs (plus at most one organization-currency GET if needed), with the client's maximum three attempts and bounded backoff inside a 30-second report-operation deadline. Add a configuration-owned per-session limit of three comparisons per minute; returning a throttled error never starts a read. These proposed controls require implementation tests, including cancellation and shared parent budgets.

Xero timeout/rate-limit/unavailable responses produce sanitized transient errors with deliberate retry guidance and no invented briefing. Missing consent/permissions returns a permission error and reconnect guidance. Invalid period input returns allowed examples. Empty reports show “no report data”; unsupported schemas or failed reconciliation show an unsupported-data error, not zero profit. A model outage leaves the validated deterministic comparison available without generated explanation. No report path invokes `propose_action` or a Xero mutation.

Trace only AI model/tool use through existing metadata-only instrumentation: use case, pinned model, prompt hash, usage, latency, outcome, environment, and pseudonymized session identifier. Keep report rows and values out of logs/traces and offline artifacts; record unavailable billing as unavailable. Preserve existing sampling and 30-day retention policy. Use a feature flag disabled until fixture tests and authorized demo preflight pass; disabling narration must retain deterministic output. Rollback the prompt/flag rather than adding infrastructure.

## Delivery gates and future verification

1. **Data/access preflight, before implementation commitment:** a person connects the Demo Company with the required granular scope and verifies the organization, base currency, permissions, standard layout, and two completed months with a meaningful profit/account movement. Compare the API periods/basis against Xero's matching report settings. Do not print tokens or commit raw reports. If no suitable live data exists, use clearly labeled synthetic fixtures for development and revisit the live-demo plan; never present fixtures as live company results. No preflight has been performed for this discovery.
2. **Deterministic adapter and calculation:** offline HTTP fixtures for nested sections, duplicate labels, account alignment, summary-row double counting, negative/zero baselines, signed income/expense movements, rounding, missing cells, empty responses, malformed dates, changed layouts, oversize data, and full reconciliation. Test permission/throttle failures, bounded retries, cancellation, result truncation labels, and no mutation calls. Do not derive P&L numbers from invoice summaries.
3. **AI integration:** mocked-model tests and a separate `profit_variance` deterministic golden dataset for routing, exact evidence attribution, numerical faithfulness, “why” uncertainty, follow-up context loss, personal account labels, instructions hidden in report labels, guardrail failure, provider outage, and no writes. A separate judge dataset measures clarity/usefulness; judge approval cannot override failed evidence or numerical assertions. Run an offline PR smoke set first; any later paid smoke needs explicit opt-in and existing bounded evaluation budgets. Retain only sanitized trend summaries.
4. **User-run demo acceptance:** ask for two known months; see totals and top contributors that reconcile to Xero, expand a source row, ask about the largest expense movement, and receive an uncertainty statement about its cause. Demonstrate an empty/unsupported result or provider outage with an honest fallback. No write confirmation or new Xero record appears. Target a 15-second warm happy-path result on the demo setup; measure before claiming it. UI/browser acceptance remains user-run.

The discovery is complete when this recommendation, alternatives, evidence, MVP, and gates are reviewable. Runtime docs should change only when implementation actually changes product behavior.
