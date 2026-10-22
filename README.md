# Ledger

### A conversational assistant for Xero

Ledger lets you ask questions about a company's invoices and turn a request into a change you can review before it reaches Xero. It combines a chat interface with contact browsing and an invoice editor, using Xero's Demo Company for real API integration.

I built this project to explore a practical question: **how do you give an AI assistant useful access to financial software while keeping people in control of changes?**

## What you can do

- Ask which invoices are overdue, check unpaid totals, or compare invoice totals across two periods.
- Find a customer or inspect an invoice without navigating Xero manually.
- Request a new contact or create, update, or void an invoice through chat. Ledger presents a confirmation card before executing each action.
- Review and edit invoices directly in the UI.
- Reopen saved conversations and continue with requests such as “use the same contact.”

For example, **“Create an invoice for Bob's Construction for $200 of consulting”** starts with a contact lookup. Once the required details are available, Ledger presents the proposed invoice. You can add a reference or change the due date on the card, then confirm it. If the contact doesn't exist, creating that contact requires its own confirmation first.

Invoice edits send only changed fields. Clearing the reference is supported; clearing a due date requires Xero. Existing lines keep their identities, accounts, tax, tracking, and supported discount details. The editor explains unsupported line formats and keeps their metadata editable. Amounts on lines with explicit tax must be edited in Xero because Ledger cannot safely identify manual tax overrides. Chat line edits use exact original description, quantity, and price selectors. The server resolves unique matches to private Xero identities before proposal; ambiguous or changed lines require reloading or the invoice editor. Confirmation explanations use bounded narration.

## Performance reports

The Performance page compares two read-only, standard-layout accrual P&Ls. It defaults to the last two completed calendar months in the connected organisation's timezone. Choose a current range and compare it with the previous period, previous year, or a custom range. Whole calendar months compare with the previous calendar month; other previous-period ranges use the same number of days. Previous-year dates clamp leap day to the prior February end. Unequal-length periods are labelled. Dates, base currency, basis, timezone and each report's retrieval time remain visible. This reporting view has no generated explanations or accounting writes.

The comparison shows income, expenses, net profit and account movements with exact decimal-string amounts. The five largest signed contributions plus the other-movements/rounding remainder reconcile to reported profit change. A negative expense credit can increase profit. Percent changes are unavailable when the baseline is zero or negative. Accounts align by private Xero identity, so duplicate labels and renamed accounts do not split or merge them. Source links expand the correct original report section and move keyboard focus to its row; neither source report is silently flattened into totals. Separate reads are not an atomic accounting snapshot, and account movements alone do not establish business causes.

The Balance sheet tab compares assets, liabilities, equity and net assets at two as-of dates. It defaults to the last two month ends in organisation time; choose previous month, previous year or custom dates. End-of-month presets preserve month ends, other previous-month choices preserve the day where possible, and leap-year dates clamp safely. Nested or flat supported standard sections retain their source hierarchy. All category totals and assets minus liabilities equals equity must reconcile before account alignment. Negative asset/contra accounts retain their signs. Largest position changes are ranked by absolute amount; they are not profit contributions or cash-flow explanations. Tabs support arrow/Home/End keyboard navigation and ignore late responses after switching.

Reporting is disabled by default. Set `PERFORMANCE_REPORTS_ENABLED=true` for an authorised Demo Company access check, then match dates, basis and source figures against Xero before enabling it for the demo. Restart the backend after changing environment settings. Reconnect Xero to grant `accounting.reports.profitandloss.read` and `accounting.reports.balancesheet.read`; an existing connection alone does not establish report consent. The connected user must also have report permissions. Chat explanations are follow-up work.

Authenticated `GET /reports/profit-and-loss` accepts optional `date_from` and `date_to` together as YYYY-MM-DD. Missing both selects the last completed month. Future or reversed ranges fail. The browser uses the Next.js proxy. Responses use schema version `1`, decimal-string amounts, public source-row keys and currency precision metadata; private Xero account identities are excluded.

Authenticated `GET /reports/profit-and-loss/comparison` accepts `date_from`, `date_to`, and `preset=previous_period|previous_year|custom`. Custom comparisons require `comparison_from` and `comparison_to`; other presets reject those extra dates. Missing current dates default in organisation time. Distinct ranges must start in 1901 or later and end no later than today. One comparison performs at most three bounded GETs (organisation metadata and two reports) within the same 30-second operation deadline. Unsupported section meanings, inconsistent subtotals/profit, ambiguous identities and incomplete data fail explicitly. If either report is empty, no profit delta or account changes are inferred.

Authenticated `GET /reports/balance-sheet/comparison` accepts `as_of` and `preset=previous_month|previous_year|custom`. Custom requires `comparison_as_of` and an explicit `as_of`; presets reject an explicit comparison date. Both dates must be distinct, at least 1901, and no later than today in organisation time. P&L range parameters are rejected by this endpoint, and position parameters are rejected by P&L endpoints. The backend requests each position independently with `periods=0`, standard layout and accrual basis, verifies its one date column, and retains the same three-read/deadline/size limits. Empty data yields no inferred position change. Unsupported or ambiguous layouts—including rows without trusted account identities—fail with guidance to inspect Xero.

Each report uses at most one organisation read and one report read, each with a 1 MiB decoded-byte cap before JSON parsing, at most 500 account rows and a whole-operation `REPORT_TIMEOUT_SECONDS` budget (default 30, maximum 60). Existing Xero read retries remain bounded to three attempts within that deadline. Missing access prompts reconnection; oversized, malformed, unsupported or unavailable reports never become inferred zero totals. An explicitly empty report has no profit amount. Streams close on rejection/cancellation; no raw report is persisted, logged, traced or sent to an AI provider by this page.

The initial parser supports English standard report rows with trusted account identifiers and verified month/range headings (including Xero's documented end-date heading plus full-range title). Base currencies have an explicit supported precision policy; supported codes currently include AUD, NZD, USD, CAD, GBP, EUR, SGD, HKD, ZAR, INR, PHP, CNY, JPY, KRW, BHD, KWD and OMR. Windows-style organisation timezones are explicitly mapped for supported demo regions; unsupported currency/timezone/layout returns recovery guidance rather than a guess. Live Demo Company report access and visual/manual QA remain human-run release checks.

## Engineering decisions

**Keep the write boundary in application code.** The model can look up records and propose an action, but it cannot execute a Xero write. FastAPI validates the proposal and handles execution after a person confirms it. The invoice editor uses the same service and validation rules.

**Make confirmations safe to repeat.** SQLite atomically claims each confirmed write and freezes its payload. Repeating a successful confirmation returns its saved result; a competing confirmation or denial cannot execute it again. Editor saves retain a request identifier when their response is lost. Xero requests use bounded retries with the same idempotency key. An uncertain outcome is quarantined for a person to check in Xero before starting another write.

**Give agents focused responsibilities.** A PydanticAI orchestrator handles the conversation and proposals. A separate agent handles contact and invoice reads through purpose-specific MCP tools. Neither needs arbitrary database access.

**Treat money as decimal data.** The backend validates quantities, unit prices, and totals with explicit precision and size limits. Decimal values are sent to Xero as strings to avoid rounding introduced by binary floating point.

**Protect data before model calls.** Personal values are replaced with placeholders in prompts, conversation history, and tool results, then restored inside the application. Secrets are masked separately. Deterministic checks and optional Jev screening address malicious input; regression cases include instructions hidden in contact notes.

**Keep the infrastructure small.** Next.js and FastAPI run in two Docker containers. SQLite stores conversations and pending actions; Xero remains the source of truth for contacts and invoices. Older conversation turns are summarized to limit the context sent to the model.

## Stack and architecture

| Layer | Technology |
| --- | --- |
| Interface | Next.js, React, TypeScript |
| API and validation | FastAPI, Pydantic |
| AI and tools | PydanticAI, MCP, OpenAI; optional Jev screening |
| Integration | Xero API, OAuth 2.0 |
| Persistence | SQLite, SQLAlchemy |
| Development and testing | Docker Compose, pytest, Pydantic Evals |
| Optional model tracing | Langfuse |

The browser communicates with Next.js, which proxies API requests to FastAPI. The backend owns authentication, agent execution, persistence, and Xero access.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request flow and confirmation sequence.

## Testing the assistant

The tests cover authentication, action confirmation, invoice validation, Xero OAuth, conversation state, and data redaction. Agent evaluations exercise both individual requests and follow-up conversations.

Evaluation cases include ambiguous or missing details, optional invoice fields, denied actions, prompt injection, and attempts to claim an unconfirmed write succeeded. Deterministic checks inspect tool calls and results alongside model-based judging. A judge's approval alone cannot pass a case that required a proposal the agent never made.

The datasets and evaluation runners are in [backend/evals](backend/evals); API and regression tests are in [backend/tests](backend/tests). Live model evaluations require provider credentials and incur API usage costs.

## Run locally

Run Docker Compose directly from an Ubuntu terminal with Docker Engine and the Compose plugin installed and the daemon accessible to your user. Project dependencies run inside containers. Configure a local `.env` using [.env.example](.env.example); a connected demo needs Xero OAuth credentials and an OpenAI API key.

```bash
cd /home/jarrod/Desktop/xero_assistant
cp -n .env.example .env
docker compose up --build
```

Open [localhost:3001](http://localhost:3001). The backend runs on port 8000.

To rebuild both images without starting the app, run `docker compose build`. Source files are bind-mounted for development; polling remains enabled for reloads. After changing npm dependencies, run `docker compose run --rm --no-deps frontend npm install` to update the dependency volume and commit the updated lockfile. Frontend image builds use `npm ci` to install that locked dependency tree. Check dependency security with `docker compose run --rm --no-deps frontend npm audit`.

Docker named volumes are local to each computer. Moving the repository does not transfer the SQLite database (`assistant-data`) or frontend dependency/cache volumes. Restore a database backup if you need the previous conversations and Xero connection; otherwise sign in and connect Xero again. Rebuilding images preserves existing volumes. Avoid `docker compose down -v` unless you intend to delete local data. Keep `.env` private and do not commit it.

Run the default offline backend suite without provider credentials:

```bash
docker compose run --rm --build --no-deps backend pytest -q
```

Paid tests use the `live_eval` marker and are skipped unless `--live-evals` is present. Offline tests prohibit real PydanticAI requests and real HTTPX transports. Run a small paid smoke check deliberately, or opt in to all five live datasets:

```bash
docker compose run --rm --no-deps backend python -m evals.orchestrator.run --live --scoring deterministic --case unpaid_total
docker compose run --rm --no-deps backend pytest -q --live-evals -m live_eval
```

The invoices runner supports the same flags. Jev uses `python -m evals.jev.user_message.run --live --case unpaid_total` and requires `TYPESAFE_API_KEY`. Judge runs require `--scoring judge` and use the configured `MODEL` for both answers and judges. Prefer a provider snapshot identifier when measuring regressions; the current model defaults are aliases, so they do not guarantee an immutable snapshot.

Each dataset allows two concurrent cases, 90 seconds per task, and 900 seconds for the whole evaluation including judges. Agent tasks allow 12 requests, 12 tool calls, and 20,000 tokens per case; start with one deterministic case (at most 20,000 task tokens) and review provider billing before expanding. Judge and Jev usage is outside that token budget. A full run selects 71 cases and can incur substantial usage; no live evaluation is run by normal pytest or production chat.

JSON artifacts in `backend/evals/artifacts/` contain dataset/prompt hashes, framework version, configured and observed task models, task usage, assertion outcomes, and latency. They omit prompts, outputs, reasons, and exception text. Cost is recorded as unavailable rather than zero because the runners lack billing data; judge/Jev usage is also unavailable. Artifacts are git-ignored local evidence; delete them after 30 days and retain only reviewed summaries when publishing results. Failed assertions, task/evaluator exceptions, empty reports, duplicate cases, and missing cases all fail the run.

Frontend regressions run without a browser or provider credentials:

```bash
docker compose run --rm --no-deps frontend npm test
docker compose run --rm --no-deps frontend npm run build
```

Confirmed writes have a 120-second execution deadline, configurable with `ACTION_EXECUTION_TIMEOUT_SECONDS` (greater than 0, at most 240). If a card says **Outcome unknown**, check Xero before requesting another change. **Check status** reads the saved receipt and never repeats the write. See [ARCHITECTURE.md](ARCHITECTURE.md) for recovery details and idempotency limits.

Chat turns have a 60-second deadline covering preparation, summary updates, screening, model calls, and tools. Parent and invoices-agent work share limits of 12 model requests, 12 tool calls, and 20,000 reported tokens. Each model request asks for at most 2,048 output tokens and has a 20-second provider timeout. Token totals are checked after responses; a response can exceed the remaining token allowance, after which no more model/tool work is permitted. New messages are limited to 4,000 characters. These defaults and validated environment settings are listed in `.env.example`.

Production chat uses the `openai:` provider with SDK retries disabled (`AI_PROVIDER_RETRIES=0`, the only accepted policy). Failures are surfaced for a deliberate retry; the app does not replay a model turn that may already have proposed actions. Model validation gets at most one retry, counted in the shared budget. Set `CHAT_TEMPERATURE=null` when the configured model does not support temperature.

Summary work allows one fold per turn by default, with a 10-second deadline, two requests, 4,000 tokens, and 768 output tokens per fold. A failed fold retains the last saved summary and its coverage. History sent to the model keeps at most 20 recent stored messages and 12,000 characters, plus the 2,000-character summary. If earlier details are missing, the model is told to ask for them. `CHAT_SUMMARY_EVERY=0` disables folding while retaining bounded history. Configured Jev screening has a five-second deadline and fails closed on timeout or provider failure.

Timeouts, exhausted budgets, invalid model responses, outages, and rate limits end the stream with safe recovery guidance. **Stop reply** cancels an unfinished response. Any already-saved proposal remains available when the conversation is reopened; streaming failure does not execute it. Browser acceptance remains user-run.

Optional Langfuse export samples 10% of AI workflows by default and exports metadata only: model/tool names, reported tokens, span latency, prompt-source hashes, environment, outcome, and an HMAC conversation identifier. Prompts, replies, arguments, tool results, exception bodies, and unrelated HTTP/database spans are excluded. Billing costs remain unavailable. Configure a 30-day retention policy in the tracing deployment/account before enabling it; the app does not automatically delete remote traces. Offline tests disable export. No new tracing service is required.

## Project scope

Ledger is a portfolio project built around one connected Xero Demo Company and shared demo sign-in. Its implemented workflows cover contacts and sales invoices. Production multi-tenant access, broader accounting workflows, and production deployment are outside the current scope.

## Currency totals and bounded reads

Invoice lists and totals use response schema `2`. Summaries and period comparisons report an alphabetically ordered `currencies` array; AUD 100 and USD 100 remain two amounts. There is no exchange-rate conversion or mixed-currency grand total. Empty results have an empty array, with no assumed currency. Comparisons align the currencies occurring in either period and use zero for a currency absent from one period. Totals require valid invoice currency codes.

Each Xero invoice read retains at most 2,000 invoices and fetch one extra page only when needed to distinguish an exact-cap result from truncation. Lists expose `complete`, `scanned_count`, `limit`, and `next_step`. Partial lists are labelled in the UI; their emptiness cannot prove no invoices exist. Summaries and comparisons reject incomplete reads and ask for narrower contact, status, or date filters. Contact searches are also bounded; invoice contact filters resolve up to 100 matching contact IDs and apply them in Xero before the invoice cap. Comparisons query each requested period separately (at most 2,000 invoices per period), excluding irrelevant gap dates and deduplicating overlaps. Reversed date ranges are rejected. Browser acceptance remains user-run.

The invoices deterministic dataset now includes synthetic mixed-currency summary/comparison, empty, truncated-summary, and truncated-list cases with mechanical answer checks. To run one paid case deliberately:

```bash
docker compose run --rm --no-deps backend python -m evals.invoices.run --live --case mixed_currency_summary
```

Offline tests verify the math, HTTP/MCP contracts, cap boundaries, evaluator checks, and actual list-page interactions. No live evaluation or Xero verification is implied by those tests.
