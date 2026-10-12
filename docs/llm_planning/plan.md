# Domain-owned subagents

The chat model is an orchestrator. It owns the conversation and `propose_action`. One invoices subagent owns the reads, including contact lookup. A person still confirms before anything is written.

Do the phases in order. Run tests with Docker Compose from Ubuntu, as in `.cursor/rules/docker.mdc`.

## Harness

**Subagents: use.** `SubAgents` hands a self-contained task to a named child. The child has its own history and does not inherit the parent's tools. The only child is `invoices`. It owns `find_contacts`, `find_invoices`, `get_invoice`, `summarize_invoices`, and `compare_invoice_totals`. Contact lookup stays there because this chat uses a contact to invoice them or to see whether they already exist. The tool module stays in `backend/app/mcp_server/tools/contacts/`. A later domain that is not invoice work gets its own subagent. Contacts become their own agent only when chat has contact work that is not in service of an invoice.

`propose_action` stays on the orchestrator, including `create_contact`. It is the confirm-before-write gate. The parent calls it after the invoices agent reports back. `max_depth` is 2, so the child is not given `delegate_task`. `max_calls` on the invoices agent is 3. `contain_errors` is on, so a child crash becomes a bounded retry. Do not use `include_self`, disk agent folders, or a per-delegation model menu.

**Thinking: do not use.** It turns on provider reasoning for every model request, including each child hop. The routing rules are short and live in the orchestrator instructions.

**Planning: do not use.** It is a model-owned checklist for long runs. A chat turn is one question or one proposal. Pending writes already live in SQLite, and the confirmation card is the step the person sees.

## Phase 1 — Orchestrator and the invoices agent

Build the invoices child and the `SubAgents` roster. The parent tools are `delegate_task` and `propose_action`.

### Tasks

1. **Split the toolsets.** The orchestrator toolset is `propose_action` only. The invoices child gets the five read tools. Tool functions stay in their current modules.
2. **Instructions.** The orchestrator delegates lookups and summaries. The child returns names and amounts. It does not propose and it does not talk to the person.
3. **Tests.** An invoice question delegates to `invoices`, and that child calls `find_invoices` and can call `find_contacts` on the fake gateway. The child has no `propose_action`.

### Done when

Those tests pass offline, and a scripted create flow delegates the reads, then the parent calls `propose_action` itself.

## Phase 2 — Write boundary

The ask-once, skip, and one-proposal rules stay on the orchestrator. Confirm and deny stay on the HTTP path.

### Tasks

1. **Ask once.** A missing reference or due date produces one question and no `propose_action`. Say that a blank due date means 14 days from today.
2. **Skip proposes.** When the person says to skip, the orchestrator calls `propose_action` with `create_invoice` and does not delegate that call.
3. **One proposal.** The parent stops after storing one pending action. The child never sees `propose_action`.

### Done when

A scripted skip turn calls `propose_action` with `create_invoice`, and a scripted missing-reference turn asks once and does not propose.

## Phase 3 — Golden datasets

The orchestrator and the invoices agent each have a dataset. Pytest scores each one twice, and both runs call the configured chat model. Deterministic scoring compares the answer and tool trace with the case expectations. Judge scoring sends the answer to a judge model with that case's rubric. A chat request does neither.

### Tasks

1. **Orchestrator cases.** `backend/evals/orchestrator/golden.yaml` names `expect_delegate` as `invoices` or `none`, and whether `propose_action` is expected. Cover unpaid, overdue, Bob's Construction, period comparison, denial, a confirmed execution, skip-means-propose, ask-once, an out-of-scope refusal, and an instruction hidden in a contact note.
2. **Invoices cases.** `backend/evals/invoices/golden.yaml` names the read tool. Cover unpaid, overdue, contact lookup, period comparison, one invoice number, and an instruction hidden in a contact note. The child never proposes.
3. **Trace.** Each eval task appends a tool trace after the answer. Deterministic checks read that trace. A dataset-shape test fails if a case is missing or renamed.

### Done when

Superseded by quality-remediation Phase 3: ordinary `pytest` runs offline dataset-shape and report-integrity checks. Paid scoring requires `--live-evals -m live_eval` or runner `--live`; a missing or renamed case still fails the shape test.

## Phase 4 — Offline LLM judge and the Jev filter

The LLM judge scores a golden dataset. It is not part of a chat request. Jev is the live malicious-input filter on the orchestrator. It screens the user message before the chat model runs. It is not an evaluator.

### Tasks

1. **LLM judge.** Every orchestrator case and every invoices case has an `LLMJudge` rubric. Each dataset has a `G-Eval` rubric. Amounts and invoice numbers in the tool trace count as evidence. A write claim still fails when the user message has no execution result.
2. **Separate score.** The judge run keeps `LLMJudge` and `G-Eval` and drops the expectation checks. The deterministic run does the opposite. A chat request does neither.
3. **Jev filter.** When `TYPESAFE_API_KEY` is set, the orchestrator input guardrail calls Jev once on the user message and refuses the turn on block, review, or a self-harm support route. Do not add a Jev evaluator to either dataset.

### Done when

Both datasets contain an LLM judge on every case and expectation checks beside it. Pytest runs those as two scores. The chat request path runs neither.

## Phase 5 — Docs

Update `ARCHITECTURE.md`, `backend/app/chat/AGENTS.md`, and `backend/evals/AGENTS.md` so they show the orchestrator, the invoices delegate, `propose_action` on the orchestrator, Jev as the live input filter, and the two golden datasets.

### Done when

`docker compose run --rm --build --no-deps backend pytest -q` passes from Ubuntu, and the running agent is the harness `SubAgents` roster.
