---
name: workflow
description: Deliver a Careergrind Kanban item through requirements discussion, approved planning, small reviewable tickets, TDD implementation with human approval after each ticket, two blind reviews, and a PR for human QA. Use when asked to start or resume this delivery workflow, including a named Kanban item.
---

# Workflow

Own delivery and its recorded state. This skill contains its planning, ticketing, TDD, and review instructions; no other skills are required. Write artifacts in plain language. Keep workflow records local to the primary checkout and product changes isolated in worktrees.

## Select and resume

- Read applicable `AGENTS.md` files and existing artifacts. Inspect relevant code. Consult `docs/testing.md` for checks, `GLOSSARY.md` for terms, and architecture docs/ADRs when affected contracts require them.
- Preserve unrelated changes. Resume existing plans, approvals, tickets, and branches; reconcile records with actual files, commits, and checks instead of restarting.
- Leave the item on the board until the human explicitly confirms completion. Checks, reviews, and a PR do not establish human acceptance.
- For research-only work, investigate primary sources and record cited findings and open questions in `docs/plans/<feature-slug>/research.md`. Do not infer authorization to implement recommendations.

## Artifacts and progress

Use a stable lowercase hyphenated feature slug; honor user-supplied names and branches.

- Plan: `<primary-checkout>/docs/plans/<feature-slug>/plan.md`.
- Tickets: one combined `<primary-checkout>/docs/plans/<feature-slug>/tickets.md`, with stable numbered ticket headings. Never renumber existing tickets.
- Integration branch: `work/<feature-slug>`.
- Worker branches: `work/<feature-slug>-<NN>-<ticket-slug>`, each in its own worktree.

Resolve the primary checkout from `git worktree list --porcelain`; it is the non-bare worktree whose Git directory is the common Git directory. Confirm `KANBAN.md` and `docs/plans/` are ignored with `git check-ignore` before writing them. They are local-only coordination state: never force-add, commit, or copy them into worktrees. If legacy artifacts are tracked, preserve their working copies and remove them from the index as a workflow-maintenance change, not in a product PR. The coordinator alone updates these records; pass absolute paths as read-only context to workers.

After both approvals, create the integration branch from the selected base and record that base in the local plan. Honor an explicitly supplied base branch instead of assuming master. Do not switch a dirty checkout or overwrite unrelated branches.

Maintain a compact delivery record in the plan: source item, phase/next action, actual human approvals tied to the approved revision or content hash, integration base/head, branches, ticket dependencies/statuses, actual verification results, review snapshots/outcomes, and PR/manual-QA handoff. Record blockers and unfinished work for resumption. Agent summaries are not new human approvals.

Ticket states: `ready-for-agent`, `in-progress`, `blocked`, `awaiting-human-review`, `implemented`. Awaiting human review means the ticket is implemented and verified on its own branch, with a ticket-scoped draft PR presented for review; it is not yet integrated. Implemented means the human approved that ticket's reviewed revision and it has been integrated, not acceptance of the overall item. The coordinator owns integration, ticket status, board updates, and PR work.

## Explore and settle decisions

Before writing the plan, inspect the code and interview the user until the product and delivery decisions are explicit. Treat discovery as a decision tree, not a request for one general clarification:

1. Start with the root decisions: the concrete problem, who experiences it, the desired outcome, and scope boundaries. State what the code already establishes and list any tentative assumptions; do not quietly promote an assumption into a requirement.
2. Build the next question frontier from decisions whose prerequisites are settled. Ask the whole useful frontier in one round, number the questions, and give a recommended answer with reasons for each. Phrase each question so a plain “yes” accepts the recommendation. Do not ask a downstream question while its parent decision is unresolved.
3. After every answer, update the decision tree. Answers commonly expose new branches; ask those in a later round instead of treating the first round as sufficient. Continue inspecting repository facts independently while the user answers.
4. Distinguish facts from choices. Find codebase, environment, and existing-behavior facts yourself. Ask the user to choose behavior, tradeoffs, boundaries, and priorities that cannot be derived from evidence.

Probe each relevant lens below. Skip a lens only when repository evidence or an earlier answer makes it genuinely irrelevant; record that reason rather than silently omitting it.

- current pain and a concrete example;
- primary user, trigger, happy path, and definition of success;
- inputs, outputs, state transitions, UI/API behavior, and wording users will see;
- empty, invalid, partial, duplicate, retry, cancellation, timeout, and dependency-failure behavior;
- authorization, tenant boundaries, privacy, sensitive data, and destructive effects;
- compatibility, existing in-progress data, migration, rollout, and rollback;
- concurrency, idempotency, ordering, ownership, and cross-service boundaries;
- observability, cost or performance limits, and operational recovery;
- acceptance evidence, automated test seams, manual QA, and explicit out-of-scope behavior.

Discovery is complete only when the decision frontier is empty: all relevant branches are answered, deliberately deferred, or explicitly out of scope; remaining assumptions are visible and accepted; and the user confirms a concise shared-understanding summary. A single broad question or an agent-authored summary is not enough when unresolved branches remain. Shared-understanding confirmation is not plan approval. Record settled choices, deferrals, rejected alternatives that constrain implementation, and open questions. Do not invent requirements to fill headings.

Prefer deep modules: useful behavior behind a small, simple interface that hides complicated details. Keep responsibilities cohesive and dependencies directed toward the owning module. Avoid callers managing internal sequencing/state, shallow wrappers, speculative abstractions, and duplicated decisions. Prefer existing public test seams and the highest useful observable interface. Update shared terminology and justified architectural decisions using repository glossary/ADR conventions when needed.

## Plan and approve

Write the plan with these sections, scaled to actual scope:

- Problem Statement
- Human Decisions
- User Stories
- Solution
- Implementation Decisions
- Testing Decisions
- Architecture Decisions
- Rollout Risks and Other Risks
- Observable Acceptance Criteria
- Dependencies and Verification
- Out of Scope
- Additional Notes
- Delivery Record

Describe the problem and solution from the user's perspective. Include relevant module/interface decisions, schema/queue contracts, test seams and existing test examples, verification commands, and a manual-QA outline. Prefer durable descriptions over speculative file inventories; include precise contract snippets when they communicate an agreed decision better than prose.

Present the written plan and test seams. Obtain explicit human plan approval before drafting tickets. Record the approved revision. Material scope/design changes require renewed approval; routine implementation choices and in-scope fixes do not.

## Break down and approve

DO NOT OVERCOMPLICATE THE DESIGN

After plan approval, draft tickets in the single tickets file. Present reviewable outcomes, granularity, verification evidence expected, and blocking edges. Obtain explicit human breakdown approval before implementation or creating the integration branch. Plan approval does not imply breakdown approval. Record the approved revision; material breakdown changes require renewed approval.

Choose the smallest coherent, reviewable slice that fits a fresh agent context and has clear verification evidence. A ticket may cover an interface, prefactoring, or one layer without delivering an end-to-end behavior. Use a vertical slice when it is the smallest meaningful review unit. Order tickets to expose uncertain design decisions early, so the human can redirect or abandon a bad design before more work builds on it. Prefactor first where it makes the approved change easier.

For wide mechanical refactors, use expand–contract: introduce the new form alongside the old, migrate callers in bounded reviewable batches, then remove the old form after all migrations. Keep intermediate tickets green where possible. If they cannot stay green, document the limitation and required final integration checks in the approved breakdown and each affected review draft.

Each numbered ticket contains:

- **What to build:** coherent change and reviewable outcome.
- **Blocked by:** stable ticket IDs or None; only genuine prerequisites.
- **Layers:** layers actually affected.
- **Modularity:** relevant ownership, public interface, and test seam decisions.
- **Status:** one of the states above.
- **Acceptance Criteria:** observable, checkable outcomes.
- **Verification:** intended commands, then actual commands/results and red/green evidence.
- **Progress:** assigned branch/worktree, starting base, resulting commits, blockers, and concerns.

Keep implementation tickets off the overall Kanban board. After breakdown approval, create or resume the integration branch; planning artifacts remain ignored local workflow state.

## Implement with subagents

Implement one ticket at a time, including independent tickets. Do not start or delegate the next ticket until the human explicitly approves the current ticket's reviewed revision. Give the worker a separate worktree and branch based on the current integration head.

Give workers relevant plan/ticket context, repository instructions, acceptance criteria, branch/base/worktree details, and the TDD instructions below. Workers stay within approved scope and their worktree. Require changed files/commits, acceptance outcomes, actual red/green and broader check results, and concerns. Workers must not mutate the integration branch, combined tickets file, board, or PR.

Inspect the completed ticket's branch diff against its recorded starting integration head, resolve issues without discarding unrelated work, and verify acceptance criteria on that branch. Run the ticket's focused checks, then follow the per-ticket review checkpoint. Only after human approval, integrate that ticket's commits, verify the integrated result on the integration branch, and mark it implemented before releasing the next ticket. Record failures truthfully and investigate fixable ones; unrun checks cannot count as passed. Ask about material ambiguity or external blockers while continuing independent work within the current ticket.

### Per-ticket human review

After each ticket, create a separate draft PR for that ticket alone, targeting the integration branch. Its base is the integration head recorded when the ticket started, so its diff shows only that ticket's work. Do not add later tickets or the combined feature result to this PR. Present the ticket's diff, design rationale, actual verification results, and remaining limitations. Record the PR, ticket base/head commits, and `awaiting-human-review` status in local workflow state. Verify the diff excludes `KANBAN.md` and `docs/plans/` before publication. If PR tooling is unavailable, present the local diff and exact commits as the review draft and report the blocker.

Stop and wait for explicit human approval of that revision before beginning any subsequent ticket. Plan approval, breakdown approval, passing tests, and agent reviews do not satisfy this checkpoint. Address requested revisions within the current ticket, rerun affected checks, and present the revised draft for approval. If the human redirects or abandons the design, record that decision and revise the remaining plan/tickets as needed; obtain renewed approval for material changes.

Record approval against the reviewed head commit. Integrate the approved ticket, then mark it implemented and only then continue to the next approved ticket. Keep each ticket PR limited to its own review; never reuse it for later tickets. After every ticket is approved and integrated, the complete feature can be assembled and reviewed as a whole through the final two blind reviews and final human-QA PR. These checkpoints supplement each other.

### TDD instructions for workers and review fixes

Read repository instructions and existing tests. Implement one observable acceptance behavior at a time through a real interface:

1. **Red:** Write and run one focused test. Confirm failure because behavior is missing; setup errors do not count. If it already passes, find an uncovered requirement instead of forcing failure.
2. **Green:** Make the smallest production change that passes the test and rerun it.
3. **Refactor:** Improve code while keeping relevant tests green. Repeat for the next behavior, then run broader checks across necessary layers and meaningful failure paths.

Test observable results, errors, saved state, or emitted work. Avoid private-method assertions and tests mirroring implementation. Stub external services at their boundary without mocking away business behavior. Add regression coverage for bugs and duplicate-delivery coverage when queue changes affect idempotency.

Run checks in Docker following `docs/testing.md`, without browser automation or browser-driven QA. Leave visual/manual checks to the human. Documentation and mechanical edits use appropriate existing/static checks instead of artificial red tests. Report actual commands/results and execution blockers.

The coordinator runs each command with the target worktree as the command's working directory; neither the coordinator nor the human should have to navigate there. When handing a command to the human from the primary checkout, use absolute paths, for example `docker compose -p <project> --project-directory <worktree> -f <worktree>/docker-compose.yml run --rm <service> <check>`. Use a unique, stable Compose project name for a worktree stack. Focused `run` checks normally need no published ports; if manual QA needs a running stack, state its project name, URL/port overrides, startup command, and teardown command explicitly.

## Worktree lifecycle

- Record every workflow-created worktree's purpose, absolute path, branch or detached commit, and cleanup state in the local plan.
- A worker worktree becomes disposable only after its intended commits are integrated, the integration branch contains them, required checks pass, and `git status --short` in that worktree is empty. Remove the worktree, then delete its local worker branch only when Git confirms it is merged. Never force-remove a dirty worktree or force-delete an unmerged branch.
- Remove detached review worktrees after their review result is captured and any test process or Compose stack they started is stopped. They do not need to survive review resolution.
- Keep the integration worktree through PR review and human manual QA so the exact candidate remains easy to run. Remove it and its local branch only after explicit human completion/merge confirmation, or earlier at the human's request after clearly reporting what will no longer be locally available.
- Before creating worktrees, run `git worktree prune --dry-run`. Prune stale administrative entries only when their paths are already missing; do not treat pruning as permission to delete live directories.
- At handoff, report the retained integration worktree path and a copy-paste test/start command from the primary checkout. At completion, report which worktrees and branches were removed and anything intentionally retained.

## Two blind reviews

After integration and relevant checks, commit the candidate and fix base/head commit IDs. Verify the full diff contains only intended work. Spawn two fresh reviewers concurrently with no inherited conversation (`fork_turns: none` when supported), one for correctness and one for design.

Give each only repository instructions, code access, the same base/head snapshot, useful non-browser check commands, and its review instructions below. Give the design reviewer the deep-module definition above. Do not send the entire workflow skill or delivery context. Explicitly prohibit reading the Kanban item, plan, tickets, acceptance checklist, implementation reports/rationale, PR discussion, commit messages, or the other review. Replace reviewers who already know that context.

Reviewers may inspect code, tests, schemas, and established technical documentation. They must not modify source, tests, tickets, or workflow state. Run useful Docker checks without browser automation, using isolated worktrees for test-generated artifacts.

### Correctness reviewer instructions

Trace changed behavior and surrounding code for incorrect results, regressions, invalid state changes, incompatible callers/schemas, and edge cases. Check authentication, authorization, tenant isolation, input handling, secrets, transactions, races, retries, duplicate queue delivery, and partial failures where relevant.

Verify repository cross-service rules: Rails owns domain writes, long-running AI work uses queues, handlers tolerate duplicate delivery, and LLM/embedding calls follow repository rules. Report missing tests when a concrete uncovered behavior creates credible bug risk. Ground defects in specific inputs or execution paths without inventing product requirements.

### Design reviewer instructions

Judge changes against actual callers and surrounding code. Check small interfaces that hide complexity, cohesive responsibilities, dependency direction, and business logic ownership. Look for duplicated decisions, callers managing internal sequencing/state, shallow layers, and unnecessary abstractions.

Assess whether tests cover observable behavior and failure paths, survive refactoring, and avoid excessive mocking or implementation-mirroring assertions. Check names, file responsibilities, descriptions, and local documentation rules. Suggest focused changes backed by concrete maintenance/test risk. Separate optional preferences and avoid unrelated refactors.

### Review output and resolution

Each reviewer returns reviewed base/head IDs, actual commands/results, and limitations. Order actionable findings by severity (P0 urgent, P1 high, P2 normal, P3 low), with file/line evidence, trigger or concrete risk, impact, and focused repair direction. Distinguish reproduced failures from code inference and label uncertainty. Explicitly state when there are no actionable findings.

The coordinator separately checks every acceptance criterion; blind review does not establish requirements completion or human acceptance. Validate findings, apply supported in-scope fixes using TDD for behavior changes, document dismissals with evidence, and rerun affected checks.

After substantial fixes to behavior, interfaces, dependencies, or test coverage, commit a new candidate and run another fresh pair of blind reviewers against the final full diff from the original base. Repeat until no actionable findings remain. For purely editorial fixes, inspect the final diff and record why another round was unnecessary. If progress is blocked, record unresolved findings and ask the human instead of claiming a clean review.

## PR and human handoff

After all tickets have been individually approved and integrated, run cross-ticket verification and acceptance checks, then complete the final blind reviews. Only after those steps, create or update a separate feature PR from the integration branch to the selected base branch, showing the culmination of all approved tickets, and mark it ready for review using available repository tooling. This final PR is the first review artifact that presents the combined feature. Invoking this workflow authorizes its branch, commit, PR, and safe worktree-lifecycle work described above. If access/tooling is unavailable, leave the reviewed branch ready and report the specific blocker. Verify the base/head diff excludes `KANBAN.md` and `docs/plans/` before publication.

Describe the concrete problem, resulting behavior, actual checks, review outcomes, limitations, and manual-QA steps. Record and report the PR link, branch, and remaining human checks. Stop at human review and QA. Do not merge, deploy, or clear the board without the relevant human instruction. After explicit completion confirmation, remove only the completed item from `KANBAN.md`.
