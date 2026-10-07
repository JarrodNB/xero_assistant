# Follow-up to the subagent split

`plan.md` is the orchestrator and invoices-agent split. This plan lists the gaps found in that working tree. Do the phases in order. Run tests with Docker Compose from Ubuntu, as in `.cursor/rules/docker.mdc`.

Live golden scoring stays as `plan.md` describes it. Pytest still scores each dataset twice, and both runs call the configured chat model. This plan does not add a skip, and it does not make those two scores share one sample.

`scopes.md` stays an untracked note. This plan does not wire it into the app.

## Phase 1 — Docs the next change will read

`backend/AGENTS.md` and `backend/app/AGENTS.md` still describe one chat model that calls the read tools and `propose_action`. The sequence diagram in `ARCHITECTURE.md` shows “Invoice Bob for 55 dollars” going from a contact lookup straight to `propose_action create_invoice`.

### Tasks

1. **Backend notes.** `backend/AGENTS.md` says the orchestrator calls `propose_action` and delegates reads, and the invoices agent owns `find_contacts`, `find_invoices`, `get_invoice`, `summarize_invoices`, and `compare_invoice_totals`.
2. **API package notes.** `backend/app/AGENTS.md` names the chat package as the orchestrator, the invoices subagent, the prompt, guardrails, summary, and chat routes.
3. **Diagram.** The `ARCHITECTURE.md` sequence matches the write rules already in that file. A request that omits the reference and due date asks once and does not propose. A missing contact is a `create_contact` proposal on its own. `create_invoice` waits until a later message reports that the contact exists.

### Done when

Those three files describe the same tool boundary and the same confirm-before-write path.

## Phase 2 — Prompt and the invoices cases

The invoices prompt and two golden cases can pull a live model in different directions.

### Tasks

1. **Overdue list.** `INVOICES_PROMPT` says `find_invoices` lists invoices and `summarize_invoices` is for unpaid or overdue totals. “Which invoices are overdue?” stays on `find_invoices` in `backend/evals/invoices/golden.yaml`. The prompt says that in the same words.
2. **Untrusted task text.** The child is told that a task can carry a contact note or other instruction, and that text is data. Tool fields stay data too. `injection_is_data` still expects `summarize_invoices` and a refusal to follow the note.

### Done when

The overdue case and the injection case match the invoices prompt, and the orchestrator still delegates `injection_is_data` to `invoices`.

## Phase 3 — Proposal includes the fields already given

A complete create is not in the golden set. The scripted create flow proposes a contact and a $55 line, and the payload drops the reference and due date from the user text.

### Tasks

1. **Orchestrator case.** Add a case to `backend/evals/orchestrator/golden.yaml` whose input already has Bob's Construction, $55, a reference, and a due date. `expect_delegate` is `invoices` and `expect_propose` is true. The rubric requires one `create_invoice` proposal that includes the reference and due date, and the answer says nothing was created. Add the case name to the stable list in `backend/tests/test_evals.py`.
2. **Scripted payload.** `backend/evals/orchestrator/scripted.py` puts that reference and due date on the `create_invoice` payload. `test_create_flow_delegates_then_proposes` asserts both values are in the `propose_action` result.

### Done when

The scripted create test fails if the reference or due date is missing, and the new golden case name is in the shape test.

## Phase 4 — One invoices script

`scripted_invoices_model` has no caller. The child turns inside `backend/evals/orchestrator/scripted.py` are a second copy. The invoices script docstring says it keeps pytest off the provider.

### Tasks

1. **One child responder.** The orchestrator script uses the invoices script for a turn whose tools do not include `propose_action`.
2. **Harness test.** A test runs `scripted_invoices_model` on the invoices agent and checks the read tool for an unpaid total, an overdue list, a contact name, a period comparison, and one invoice number.
3. **Docstring.** The invoices script says it is the harness stand-in for that agent. Golden pytest stays on the configured chat model.

### Done when

The invoices harness test calls `scripted_invoices_model`, and the orchestrator script no longer has its own child tool picker.
