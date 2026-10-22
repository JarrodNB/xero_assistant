# Chat agent

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

This package runs one chat turn. The orchestrator delegates contact and invoice reads to the invoices subagent and calls `propose_action` itself. The child does not propose. Personal data is replaced with numbered placeholders before the chat model, the summary model, and Jev. Tool arguments are restored for reads and `propose_action`. A delegated task stays tokenized. Tool results are protected again before a model reads them. API keys are redacted and are not restored. A known-phrase screen then refuses jailbreaks, physical harm, dosage questions, and clear self-harm statements. When `TYPESAFE_API_KEY` is set, Jev screens whatever that phrase screen allowed together with at most two protected preceding messages from the same conversation. Protected historical content has a combined 4,000-character budget allocated newest first. That context is request-scoped. Jev does not see the new assistant reply or the child brief.

Create proposals proceed when required details are known. Contact email, invoice reference, and invoice due date are independently optional. Mention them alongside a required clarification or the proposal without an optional-only question. Omitted invoice due dates retain the 14-day default; supplied values and resolved conversation context are preserved.

Before each parent or child model request, protect a copy of model history with the current turn's vault. A value learned from a tool result must use the same token in earlier prompt text on the next request. This keeps context-dependent personal-data detection from making an exact contact appear different. Stored originals and the confirmation write boundary remain in the trusted application.

## Packages

- `guardrails/` — protect personal data, redact secrets, refuse known phrases, then apply the strict input policy

## Files

- `orchestrator.py` — build the orchestrator, which delegates reads and calls `propose_action`
- `invoices_agent.py` — build the invoices subagent and its read tools
- `prompt.py` — orchestrator and invoices instructions, including the confirm-before-write rule
- `summary.py` — fold older messages into one stored summary of at most 2,000 characters
- `routes.py` — stream a turn and read saved conversations
## Bounded execution (Phase 4)

Confirmation follow-ups use bounded recorded-status narration without receipt or line ids. Success requires recorded status executed; pending/executing/unknown establishes neither success nor failure. Chat line proposals identify originals by exact editable values, with deterministic unique server matching and private identity binding before storage.

`execution.py` owns typed turn counters, model settings, the supported production OpenAI client, safe error classification, and prompt-source hashes. Parent and child each attach its hooks; do not inherit these hooks a second time. Count model requests and tools before execution and tokens after responses, including child calls and validation retries. Framework usage totals alone do not enforce unmanaged child limits in the installed harness.

`routes.py` puts preparation, summary, screening, model work, and tools under one deadline, with context cleanup in the stream task. Sanitize native failures before protocol conversion. Never flush a partially restored token on interruption or discard already-stored proposals. Only completed replies are saved.

Summary folding is separately bounded, defaults to one block per turn, and retains the last saved summary/coverage on a failed block. Always bound the recent stored tail, including when folding is disabled. Warn the model when earlier context is unavailable. Regression coverage lives in `tests/test_ai_execution.py`; live model evaluations remain opt-in.

Financial replies must preserve native currency codes and separate amounts. Partial reads cannot prove totals or absence; explain the limitation and request narrower filters. Empty groups imply no matching invoices, never a default currency. Prompt hashes version these instructions automatically.

## Report explanations

- `report_routes.py` — explicit top-level report_context branch, private typed selection, protected label screening, budgets and controlled SSE rendering. Ordinary invoice streaming is unchanged.
- `report_agent.py` — report-only MCP tools and strict offered-evidence/focus output validation, with no write/proposal/invoice tools.
- `report_prompt.py` — separately versioned performance-facts-v1 template; no injected values in the source/hash.
- `report_facts.py` — request-local full trusted comparison, bounded protected keys/labels/directions, exact application rendering, displayed-account remainder and cause-unknown/source/time limits.
- `report_history.py` — value-free persistence notice and removal of application-rendered report envelopes before ordinary model/summary work.

Do not send report amounts or raw trees to a free-prose agent. Model output remains private until typed validation, and only application-owned figures/sentences reach report chat. Narration is separately flagged off by default. An unavailable model/guard or exhausted model budget renders deterministic fresh evidence; unavailable source/invalid identity produces recovery guidance. Reopening history requires a new Performance selection. Report mode uses only the latest protected question and current refetched evidence, never guesses from history.
