# Codebase quality remediation plan

Date: 12 October 2026

## Purpose and scope

Address the nine findings from the codebase review and add the verification needed to present Ledger confidently as a resume project. Keep the existing Next.js/FastAPI boundary, SQLite persistence, focused agents, and human confirmation of Xero writes. The target remains one connected Xero Demo Company with shared demo sign-in.

This document is a plan, not a statement that the fixes have shipped. Deliver the phases in order, using small, independently reviewable changes. Update `README.md`, `ARCHITECTURE.md`, and affected folder `AGENTS.md` files when behavior changes. Follow the source headers and function descriptions required by the repository instructions.

Baseline from the review:

- 186 existing offline backend tests passed.
- The frontend production build passed.
- Temporary mocked probes reproduced duplicate execution of one proposal and loss of invoice-line accounting metadata. Those probes were removed after the review.
- Live model evaluations, live Xero writes, and browser UI testing were not run.

## Phase 1: Make writes safe under concurrency and network failure

Implementation status: delivered for local automated verification on 12 October 2026. Atomic claims, immutable confirmation payloads, durable editor receipts, bounded keyed HTTP retries, write deadlines, uncertain outcomes, restart quarantine, resource cleanup, and mocked backend/frontend regressions are implemented. No new schema is required: existing text statuses and action rows carry the receipts. Reconciliation remains manual, with read-only status checks and documented Xero verification before a new intentional action. Browser acceptance and live Xero checks remain user-run; broader application interaction coverage remains in Phase 6.

Phase 1 verification: 197 backend tests passed with `tests/test_evals.py` excluded to avoid paid evaluations; six mocked frontend receipt tests passed; the frontend production build passed. No live Xero mutations or provider evaluations were performed.

Addresses findings 1 and 5. Implement these together because retry behavior depends on knowing whether an external write occurred.

### Implementation

1. Define an explicit action lifecycle: `pending`, `executing`, `executed`, `denied`, `failed`, and `unknown`. Define which failures permit a retry; `unknown` means a write may have reached Xero and must be reconciled before another write.
2. Add a repository operation that atomically claims a pending action using a conditional database update. Claim the action and persist the validated confirmation overrides in the same transaction. Do not hold a database transaction open across a Xero request.
3. Make denial a conditional transition from `pending` only. Confirmation and denial must have one winner. All execution completion updates must check the expected state rather than overwrite any current state.
4. Return the stored result for a repeat confirmation of an executed action. For an executing or unknown action, return its current state and a useful next step. Do not call Xero again merely because a browser repeated the request.
5. Verify Xero's documented idempotency support for each write endpoint before implementing it. Where supported, persist and reuse one key for the same logical write and payload. Define behavior for key expiration and changed payloads. Where unsupported, implement reconciliation and explicitly document the remaining limitation; a local lock alone cannot guarantee exactly-once external execution.
6. Apply the same retry safety to invoice-editor create/update/void operations. Generate a request identifier for one intentional save and reuse it for retries. Prevent duplicate submissions in the frontend while a request is pending; keep the backend authoritative.
7. Normalize HTTP failures, transport failures, timeouts, and malformed responses into typed, sanitized service errors. Distinguish a rejected write from a write with an uncertain outcome. Keep useful diagnostic details in internal logs without credentials or sensitive response bodies.
8. Add bounded retry/backoff for safe reads and supported idempotent writes. Respect rate-limit responses. Never automatically repeat a potentially successful write without a valid idempotency or reconciliation strategy.
9. Define recovery for a process crash after claiming an action or after Xero accepts it but before SQLite records the result. Reconcile stale executing actions; do not simply reset them to pending.
10. Add a versioned migration for any new persisted fields. Preserve existing conversations, proposals, and results. Close owned HTTP clients and database resources through application lifespan handling.

Primary files: `backend/app/actions/routes.py`, `backend/app/actions/executor.py`, `backend/app/db/repository.py`, `backend/app/db/schema.py`, `backend/app/xero/client.py`, invoice routes/service, `frontend/components/InvoiceForm.tsx`, and `frontend/components/ChatPanel.tsx`.

### Verification and acceptance

- Two concurrent confirmations produce one gateway write.
- Concurrent confirm/deny requests cannot execute a successfully denied action or replace an executed result with denial.
- Competing confirmation overrides cannot modify an action already claimed for execution.
- Repeated successful confirmation returns the recorded result without another write.
- Timeout, connection failure, rate limit, and malformed-response tests return sanitized errors and the correct action state.
- Simulate a successful external write followed by a local persistence failure and a process restart. Recovery does not create a second invoice.
- Double submission of an invoice-editor create operation produces one logical write, and the UI shows pending and uncertain outcomes clearly.

## Phase 2: Preserve existing invoice data during editing

Implementation status: implemented on 12 October 2026. Partial update payloads omit untouched lines, existing line ids and accounting fields are retained, and additions/removals are explicit. Reference clearing uses an empty string. Due-date clearing remains explicitly unsupported. Saved responses reset the form; route generations guard late responses. Unknown line fields and ambiguous discount formats are rejected before writing. Amount edits with explicit tax require Xero because override intent cannot be determined safely. Chat line replacements without identities are rejected with an editor next step; model read results still exclude those identities. Frontend form interaction tests and a frontend lockfile were added. Phases 3–6 remain outstanding.

Phase 2 verification: 220 offline backend tests passed with `tests/test_evals.py` excluded; 14 frontend tests passed, including eight actual form interaction cases; the production build and TypeScript checks passed. No live Xero writes or paid evaluations were performed. User-run browser acceptance remains outstanding. Next: Phase 3 evaluation integrity and explicit live-evaluation opt-in.

Addresses findings 2 and 7.

### Implementation

1. Treat reference/contact/date edits as partial updates. Submit line items only when the person intentionally changes them.
2. Preserve existing Xero line identity and accounting metadata when editing lines: account, tax, tracking, discounts, and other supported fields. Preserve invoice amount conventions, such as inclusive versus exclusive tax.
3. Keep the trusted raw Xero representation in the backend. Introduce typed edit identifiers as needed to map changes to existing lines; validate that every identifier belongs to the invoice being edited. Do not make the model responsible for supplying authoritative accounting metadata.
4. Use sales defaults for new lines only. Document which line changes the editor supports and how it handles unsupported existing data. Reject an edit explicitly if it cannot be preserved safely.
5. Define omission and clearing separately. An omitted reference leaves it unchanged; an empty reference clears it. Define the intended due-date clearing behavior separately and check Xero support before implementing it.
6. Reconcile form state with the saved response so the visible fields and totals reflect Xero's result. Prevent late responses from a previous invoice from populating the current editor.

Primary files: `frontend/app/(app)/invoices/[invoiceNumber]/page.tsx`, `frontend/components/InvoiceForm.tsx`, `frontend/lib/types.ts`, `backend/app/actions/payloads.py`, `backend/app/xero/mapping.py`, `backend/app/invoices/records.py`, and `backend/app/invoices/xero_service.py`.

### Verification and acceptance

- Editing only a reference sends no replacement lines and preserves tax, account codes, tracking, discounts, line IDs, and totals.
- Editing one line preserves metadata on that line and every unchanged line; adding/removing lines has explicit tested behavior.
- Existing inclusive-tax invoices retain their amount convention.
- Clearing a reference persists after reloading; omitting it leaves the original value unchanged.
- Unsupported edits fail before an external write with a clear explanation.
- Cover the frontend save payload and form updates with interaction tests. The user performs the local browser acceptance check.

## Phase 3: Make evaluation results trustworthy and inexpensive by default

Addresses finding 3 and the review's test-workflow recommendation.

### Implementation

1. Require successful assertion values for every invoices and Jev evaluation case, using the same integrity requirements as orchestrator cases. Verify the report library's distinction between execution failures and failed evaluator assertions.
2. Reject empty or unexpectedly incomplete reports. Compare returned cases with the selected dataset so missing cases cannot create a false pass.
3. Add offline regression tests using synthetic reports with failed assertions, missing cases, and evaluator execution failures.
4. Separate paid live evaluations from fast mocked/API tests using explicit pytest markers and opt-in commands. Ordinary test runs must not call external model providers.
5. Preserve distinct deterministic and judge datasets. Keep deterministic integrity checks even when a judge approves an answer.
6. Record model snapshot, prompt version, dataset version, usage, cost, and latency with evaluation artifacts. Keep provider-facing data protected and artifacts free of raw sensitive values.
7. Document the new commands in the README and test/evaluation folder instructions. This replaces the older plan's requirement that ordinary pytest runs include live evaluations.

Primary files: `backend/tests/test_evals.py`, `backend/pyproject.toml`, `backend/evals/`, and test fixtures.

### Verification and acceptance

- One false evaluator assertion makes the associated test fail.
- Empty, partial, and exception-containing reports fail for an explicit reason.
- The default backend suite passes without real provider credentials and makes no provider requests.
- Live evaluations remain runnable explicitly, with bounded concurrency and a documented usage budget.

## Phase 4: Bound production AI execution and define degraded behavior

Addresses finding 4.

### Implementation

1. Add typed configuration for workflow duration, model-request count, tool-call count, token/output budgets, temperature where supported, and provider retry policy. Define safe defaults and validate invalid settings at startup.
2. Apply a shared turn budget across orchestrator and invoices-agent work. Verify framework accounting so child calls cannot bypass parent limits. Apply separate bounded budgets to Jev screening and summarization while keeping the overall request bounded.
3. Add a wall-clock deadline covering preparation, summary updates, screening, model calls, and tool execution. Ensure cancellation releases resources and request-scoped context.
4. Make summary failure nonfatal: retain the last valid stored summary, do not advance its covered-message count, and use a bounded recent-history fallback. Tell the assistant when earlier context is unavailable so it asks for clarification instead of guessing.
5. Define client-visible stream behavior for timeouts, provider outages, rate limits, validation failures, and exhausted budgets. Preserve already-created proposals in storage and do not narrate an unconfirmed write as successful.
6. Keep existing fail-closed behavior when configured malicious-input screening fails. Bound that screen so it cannot hang the request.
7. Trace model/tool usage with prompt versions and pseudonymized identifiers. Verify redaction of metadata and errors; document sampling and retention without adding a recurring service.

Primary files: `backend/app/config.py`, `backend/app/chat/routes.py`, agent builders, `backend/app/chat/summary.py`, guardrails, observability, and frontend stream handling.

### Verification and acceptance

- Scripted looping models stop within request/tool/token budgets, including delegated calls.
- Slow provider and tool fakes terminate within the configured deadline.
- Summary failure leaves stored coverage unchanged and still permits a bounded chat response.
- Stream errors produce a visible, recoverable UI state rather than an indefinitely busy chat.
- Cancellation resets request-scoped state; the next conversation receives no prior vault or guardrail context.

## Phase 5: Make financial totals complete and currency-aware

Addresses findings 6 and 8.

### Implementation

1. Group summary and comparison amounts by currency. Do not add raw amounts from different currencies or introduce exchange-rate conversion in this milestone.
2. Update typed gateway outputs, HTTP responses, MCP schemas, prompts, and UI displays consistently. Define zero-result behavior and deterministic ordering for currency groups. Version changed tool schemas.
3. Carry explicit completeness metadata from bounded Xero reads to their callers. Use a lookahead page or another supported signal to distinguish an exact-cap result from a truncated one without unbounded fetching.
4. Prevent definitive aggregate answers from incomplete data. Return a clear tool/API error or an explicitly partial result that the model and UI must label. Provide narrower filters or pagination as the next step.
5. Apply filters in Xero where supported so irrelevant records do not consume the result budget before application-side filtering.
6. Validate date-range ordering and expand deterministic evaluation cases for mixed currencies, empty results, and truncation.

Primary files: `backend/app/invoices/summary.py`, `backend/app/invoices/gateway.py`, `backend/app/invoices/xero_service.py`, invoice MCP tools, HTTP routes, frontend types/displays, and invoices evaluation datasets.

### Verification and acceptance

- USD 100 plus AUD 100 is reported as two currency totals, never an unlabeled 200.
- Period comparisons align currencies and explicitly handle a currency present in only one period.
- Empty results have an unambiguous response without inventing a currency.
- Below-cap, exact-cap, and above-cap reads are distinguishable.
- A truncated result cannot produce a definitive total or an assertion that no matching invoice exists.

## Phase 6: Make builds reproducible and publish evidence of quality

Known dependency follow-up from Phase 2: `npm audit` on 12 October 2026 reported eight advisories (five moderate, three high) in existing runtime dependencies: AI SDK transitive `undici`/`@fastify/busboy`, and Next.js's PostCSS dependency. The installed Testing Library/jsdom test dependencies were not the reported roots. Address these with compatible updates and verify the frontend; do not apply a forced Next.js major upgrade without reviewing migration requirements. A frontend lockfile now exists, but Docker must still be changed to consume it in this phase.

Addresses finding 9 and the review's CI, frontend-test, and resume-presentation recommendations.

### Implementation

1. Select compatible, supported versions after checking current primary documentation. Pin the AI frameworks and model snapshots; replace the floating Jev default if a stable identifier is supported, otherwise document the provider limitation and regression-check changes.
2. Commit backend and frontend dependency lockfiles. Docker builds must consume those locks, use `npm ci` for frontend installs, and pin the downloaded spaCy model. Define an intentional dependency-update process.
3. Add lightweight lint/type checks appropriate to each stack. Start with meaningful defects and manageable rules rather than a large unrelated formatting rewrite.
4. Add frontend interaction tests for confirmation/retry behavior, invoice edit payloads, reference clearing, and chat stream failures. Use purpose-built tools through Docker; do not use the IDE browser.
5. Add CI for offline backend tests, frontend tests, static checks, and the production build. Standard pull-request CI must need neither Xero nor model credentials.
6. Add an opt-in or scheduled live evaluation job with limited cases, concurrency, usage, and duration. Retain protected results for comparing model/prompt changes. Never run offline judges in production.
7. Update README setup and test instructions for the actual workflow. Document write recovery, AI degraded behavior, currency handling, completeness, model/prompt versions, and known limitations in `ARCHITECTURE.md`.
8. Add a screenshot or short user-recorded demo and publish measured evaluation results with their dates, sample counts, model versions, and limitations. Do not imply live evaluation or browser acceptance was completed when it was not.

### Verification and acceptance

- A clean Docker build uses committed dependency locks and supported pinned model configuration.
- CI passes without production secrets or paid provider calls.
- New behavior has appropriate unit/integration/interaction coverage; live eval commands are separate and documented.
- README claims match implemented behavior and retained validation evidence.
- Existing SQLite data survives schema migration and remains usable.

## Execution and release checks

Run installation, builds, and tests through Docker Compose in Ubuntu WSL at `/mnt/c/Users/Jarrod/Desktop/xero_assistant`. Rebuild the backend when dependencies change. Do not create a Windows Python environment or print `.env`.

After Phase 3, the default verification commands should be:

```bash
docker compose run --rm --build --no-deps backend pytest -q
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run build
```

`npm test` is a planned script and must be added in Phase 6. Before Phase 3 ships, explicitly select offline tests because the current default pytest suite includes paid live evaluations.

Each phase is complete only when its acceptance checks pass and its documentation describes the shipped behavior. Finish with a full offline run and user-run local UI checks for confirming/denying proposals, creating/editing invoices, clearing references, and handling errors. Any live Xero verification uses the Demo Company and explicit confirmation of each write.

## Out of scope

Production multi-tenant authentication, arbitrary accounting workflows, currency conversion, a replacement database service, and new recurring observability infrastructure. These fixes should strengthen the existing project without expanding its product scope.
