---
name: orchestrator
description: Coordinate a Careergrind Kanban item through planning, approved tickets, TDD subagents, two blind reviews, and a PR for human QA. Use when asked to start or resume this delivery workflow, including a named Kanban item.
---

# Orchestrator

Own the delivery process and its recorded state. `KANBAN.md` is the user-maintained list of overall work; ignored local Markdown files hold plans and implementation tickets. These workflow artifacts belong to the primary checkout and must not be committed or copied into implementation branches. All implementation work should be done in a worktree.

## Select and resume

- Read root and applicable `AGENTS.md` instructions, the board, and existing work for the selected item. Preserve unrelated changes.
- Use the item the user names; otherwise take the top item. If blocked, explain rather than silently selecting another. Ask if the board is empty or selection is ambiguous.
- Resume existing plans, approvals, branches, and tickets. Check recorded status against actual files, commits, and checks; do not recreate completed work.
- Leave the item on the board until the human explicitly confirms completion. Then remove only that item. Implementation, a passing review, or a PR is not that confirmation.

## Artifacts and naming

- Use a stable lowercase hyphenated feature slug. Honor user-supplied identifiers or branches.
- Resolve the repository's primary checkout with `git worktree list --porcelain`: it is the non-bare worktree whose Git directory is the repository's common Git directory. Keep all workflow state below that checkout even while implementation agents work elsewhere.
- Plan: `<primary-checkout>/docs/plans/<feature-slug>/plan.md`. Tickets: one file each at `<primary-checkout>/docs/plans/<feature-slug>/issues/01-<ticket-slug>.md`, numbered in dependency order. Do not renumber published tickets.
- Treat `KANBAN.md` and `docs/plans/` as ignored, local-only coordination state. Before writing, confirm they are ignored with `git check-ignore`; stop and fix the ignore rule if they are not. Never use `git add -f` for them, include them in commits, or copy them into an integration/ticket worktree.
- If legacy workflow artifacts are already tracked, preserve their working copies and remove them from Git's index (`git rm --cached`), then make that cleanup part of the workflow-maintenance change rather than an implementation PR. Do not delete the local records.
- Pass absolute primary-checkout artifact paths to subagents that need plan or ticket context. Only the orchestrator updates these files; implementation and review agents report results back instead of editing workflow state.
- Integration branch: `work/<feature-slug>`. Isolated ticket branches when needed: `work/<feature-slug>-<NN>-<ticket-slug>`. Reuse recorded branches on resume; never overwrite an unrelated branch.
- In the plan record the source item, phase/next action, approvals, base/head commits, branches, linked tickets/dependencies/statuses, actual verification results, review summaries, and PR/manual-QA handoff.
- Record each approval from the human's actual response, tied to the approved revision or content hash. An agent summary is not new approval. Material scope/breakdown changes require renewed approval.
- Ticket states: `ready-for-agent`, `in-progress`, `blocked`, `implemented`. Implemented means integrated and verified, not human acceptance of the overall item. Record blockers and results on each ticket.
- Create/update local `AGENTS.md` indexes as required by the repository.

## Research route

For a research-only item, read and use `research`. Give its background agent the question, relevant context, and `docs/plans/<feature-slug>/research.md` as the output path. Inspect the cited findings and report remaining questions. Do not start implementation just because research suggests changes. Await human confirmation before clearing the board item.

## Plan and approve

1. Explore relevant code and read `grilling`, `domain-modeling`, `codebase-design`, and `to-spec`. Use `to-spec` for the PRD/spec step; no separate PRD skill is required.
2. Use grilling to settle requirements and design decisions, domain-modeling to record resolved terms and justified decisions, and codebase-design to choose interfaces/test seams. Do not invent requirements to fill a template.
3. Supply `to-spec` this configuration: local Markdown tracker, the plan path above, no external publication or triage service. Use its template for the substantive spec. Add observable acceptance criteria, dependencies, verification commands, and a manual-QA outline. Proposed work is not yet `ready-for-agent`.
4. Present the written plan including test seams. Wait for explicit human plan approval before creating the branch or ticket files. Grilling agreement alone is not approval.

## Break down and approve

1. After plan approval, create/resume the integration branch and record its base commit for review and PR scope in the primary checkout's local plan.
2. Read/use `to-tickets`, configured to publish local files at the issues path above instead of `.scratch/`. Each normal ticket delivers a narrow, complete, independently verifiable behavior through necessary layers and fits a fresh agent context. Follow its prefactoring and expand–contract guidance where applicable.
3. Present the proposed tickets, delivered behaviors, and blocking edges. Wait for human breakdown approval before publishing tickets or implementing. Plan approval does not imply breakdown approval.
4. Publish individual tickets using the skill's local template, extended with progress, branch/worktree, resulting commits, test evidence, and blockers. Record the dependency graph in the plan. Keep implementation tickets off the overall Kanban list.

## Implement with subagents

- Delegate approved tickets to implementation subagents with relevant plan/ticket context, repository instructions, acceptance criteria, branch/base context, and the local `tdd` skill. Give artifact paths as read-only context and require changed files/commits, red/green evidence, actual check results, and concerns; the orchestrator alone records progress in the primary checkout.
- Run tickets concurrently only when blockers are integrated and verified. Independent dependencies do not guarantee conflict-free writes: use separate worktrees for concurrent writers, or serialize if isolation is unavailable. Assign each worker its own worktree/branch. Workers must not mutate the shared integration branch, board, or PR.
- Integrate completed ticket commits sequentially. Inspect changes and check acceptance criteria on the integration branch before marking implemented and releasing dependents. Resolve conflicts without discarding unrelated work.
- Use TDD for behavior changes and run relevant checks in Docker. Do not use browser automation, browser-driven tests, or browser QA. Non-browser component/service/integration tests are appropriate; manual QA belongs to the human.
- Record failures truthfully, investigate fixable failures, and ask about material ambiguity or external blockers. Unrun checks cannot be counted as passed.

## Test and clean up worktrees

- Run commands with the target worktree as the tool's working directory. For a human running from the primary checkout, provide an absolute-path command such as `docker compose -p <project> --project-directory <worktree> -f <worktree>/docker-compose.yml run --rm <service> <check>`; do not require manual navigation. Use a unique Compose project name for a running worktree stack, and state its URL/port overrides and teardown command.
- Record each created worktree's purpose, path, branch or commit, and cleanup state in the local plan. Check `git worktree prune --dry-run` before creating more; prune only entries whose directories are already missing.
- Remove a clean worker worktree and its merged local branch after its commits are integrated and verified. Remove detached review worktrees after capturing their results and stopping their test processes/stacks. Never force-remove dirty worktrees or force-delete unmerged branches.
- Retain the integration worktree through PR review and human QA. Remove it and its local branch only after explicit completion/merge confirmation, or earlier at the human's request after explaining what local test target will be lost. Report removals and anything retained.

## Two blind reviews

1. After integration and relevant checks, fix the candidate base/head commits and verify the diff contains only intended work. Both reviewers assess this same snapshot.
2. Spawn two fresh reviewers concurrently with no inherited conversation (`fork_turns: none` when supported). Give one `review-correctness`, the other `review-design`, plus repository instructions, code access, base/head refs, and useful non-browser check commands.
3. Do not provide the Kanban item, plan, tickets, acceptance checklist, implementation rationale, agent reports, or the other review. Instruct reviewers not to read these artifacts, PR discussion, or commit messages. Code, tests, schemas, and established technical documentation are available. Use read-only source access or isolated worktrees for test-generated files.
4. Separately check every acceptance criterion; blind review does not establish requirements completion.
5. Validate findings. Implement supported in-scope fixes as the orchestrator, using TDD for behavior changes. Document dismissals with evidence and rerun affected checks.
6. Substantial fixes (behavior, interfaces, dependencies, or test coverage) require another pair of fresh blind reviewers of the final full diff. Repeat until no actionable findings remain. If progress is blocked, record it and ask the human instead of claiming a clean review. For purely editorial fixes, inspect the final diff and record why another round was unnecessary.

## PR and handoff

- After implementation, verification, and review fixes, create/update a focused PR using available repository tooling. Invoking this delivery workflow authorizes its branch, commit, and PR work, not merge or deployment. If tooling/access is unavailable, leave the reviewed branch ready and report the specific blocker.
- Before committing or opening the PR, verify with `git status --short` and the base/head diff that `KANBAN.md` and `docs/plans/` are absent. Workflow-state changes are never part of the product PR.
- Describe the problem, resulting behavior, checks actually run, review outcomes, and manual-QA steps. State limitations plainly and exclude unrelated work from commits/PR.
- Report the PR/branch, retained integration worktree path, and copy-paste test/start command from the primary checkout, then hand off for human review and manual QA. Stop here. Do not merge, deploy, clear the board, or remove the integration worktree without the relevant human instruction.
