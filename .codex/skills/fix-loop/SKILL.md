---
name: fix-loop
description: Find and fix one concrete codebase problem per iteration, using a fresh worktree and a separate pull request for each fix. Use when the user requests an autonomous fix loop with a specified number of iterations.
---

# Fix Loop

Deliver up to the user-specified number of independent fixes. Each completed iteration means one verified fix, reviewed by a fresh subagent, committed and pushed on its own branch, with a pull request targeting the selected base branch.

## Establish the run

- Require a positive integer iteration count. If missing or ambiguous, ask for it before starting; never choose an unlimited loop. Honor any user-supplied search area, exclusions, repository, or base branch.
- Read applicable repository instructions and verification guidance. Inspect Git status, remotes, existing worktrees, and available PR tooling. Preserve existing edits and branches.
- Use the repository's remote default branch as the base unless the user specifies another. Resolve and fetch that branch; if the destination repository or base is ambiguous, resolve it before publishing.
- Invoking this workflow authorizes creating worktrees and branches, implementing fixes, committing, pushing those branches, and opening PRs within the requested scope. Follow actual tool and environment approval requirements. Do not merge, deploy, or enable auto-merge.
- Maintain a compact run ledger outside tracked product files, preferably in a unique directory under the Git common directory. Record the requested count, scope, base, iteration state, evidence, worktree paths, branches, commits, checks, and PR URLs. On resume, reconcile it with Git and the remote before repeating a mutation. Count completed PRs once.

## Repeat for each iteration

### Find one problem

Inspect relevant code and tests on the selected base. Check existing local work and open PRs for overlapping fixes, including earlier iterations. Favor bounded correctness, reliability, security, or clear user-facing defects that can be demonstrated through a concrete execution path or a focused reproduction.

Before implementing, record the problem, its trigger, supporting code or reproduction, expected behavior established by repository evidence, and a narrow verification plan. Do not treat a TODO, a naming preference, speculative cleanup, or an invented requirement as a defect. Select one root cause; its necessary regression tests and documentation belong in the same fix.

If a candidate requires an unresolved product decision, a broad redesign, or depends on an earlier unmerged fix, leave it for human discussion and look for an independent candidate. Do not stack the next PR on the previous PR to fill the count.

### Isolate and fix

Fetch the selected base and record its commit. Create a unique `codex/fix-<run-id>-<iteration>-<slug>` branch and a fresh worktree from that base. Use an available writable worktree location outside other worktrees. Run all edits and checks with this worktree as the working directory; never switch or edit the user's active checkout for a fix.

Read applicable instructions within the worktree. Demonstrate the defect with a focused regression test when behavior can be tested: confirm it fails for the intended reason, make the smallest coherent repair, and rerun it. Use appropriate static or document checks for changes that do not warrant a behavioral test. Inspect surrounding callers and failure paths, and update affected documentation or generated artifacts through their established tools.

Follow repository verification rules. In Careergrind, run application commands in Docker from the target worktree. Use `docker compose run` rather than `exec`, with a unique Compose project name for isolation. Account for test database and dependency setup; do not reuse another checkout's mounted source or reset its data. Keep secrets out of commits and do not copy production credentials into worktrees.

### Verify and publish

Run focused checks and the additional checks required for the affected area. Inspect the full diff against the recorded base for regressions, unrelated changes, generated artifacts, and secrets. Resolve supported findings before publishing. Do not claim unrun checks passed; if required verification is blocked or failing, retain the work and stop this run with the specific blocker.

Commit only the intended fix. Push the new branch without force and open one PR against the selected base. Describe the concrete trigger, resulting behavior, verification actually performed, and any remaining manual checks. Use structured PR tool arguments or a body file to preserve multiline text safely.

Check the remote for an existing PR with this head/base before creating one, especially after a timeout or uncertain response. Confirm the PR URL and remote head match the committed fix. Complete the fresh subagent review below before marking the iteration complete and beginning the next one in another fresh worktree. Do not wait for human review or merge between iterations unless the user requests it.

### Review every PR with a blank subagent

Spawn a new reviewer for this PR with no inherited conversation (`fork_turns: "none"`). Do not reuse the implementer or a reviewer from a previous iteration. Give it only repository access, applicable repository instructions, the fixed base/head commit IDs, and this review assignment. Do not provide the run ledger, problem-selection notes, implementation rationale, PR description/discussion, commit messages, or earlier review findings. If a fresh context cannot be created, stop and report that the required review is blocked.

Ask the reviewer to inspect the full diff and surrounding callers for correctness, security, reliability, maintainability, and meaningful regression coverage. It may read established technical documentation and run relevant checks in an isolated worktree, but must not edit the implementation. Require findings grounded in concrete execution paths or maintenance risks, with severity, file/line evidence, and suggested repair direction. Require the reviewed base/head IDs, actual checks and limitations, and an explicit statement when no actionable findings remain. The reviewer returns its report to the coding agent; it does not post external comments.

Assess each finding against code evidence. Fix supported in-scope issues, rerun affected checks, commit, and push without force. Record evidence for dismissed findings. After any code or test changes, obtain another blank subagent review of the full original-base-to-new-head diff, without passing earlier findings or implementation context. Continue until the final PR head has no unresolved actionable findings. If review or repair cannot converge, retain the PR and worktree, record the unresolved findings, and stop the run rather than counting the iteration as complete.

Record the final reviewed commit and review outcome in the ledger and PR description, together with actual verification limits. Confirm the remote PR head is the reviewed commit before continuing.

Retain each PR's worktree and branch for review. Stop temporary processes and containers created for checks, without removing shared resources or test data belonging to other work. Do not remove dirty worktrees or delete unmerged branches.

## Boundaries and handoff

Stop when the requested number of PRs is complete, the user stops the run, a required access/setup/check blocks completion, or a reasonable inspection of the requested scope finds no further justified independent fix. Do not fabricate problems, expand scope, repeatedly retry a blocked external action, or count skipped candidates as completed iterations. Preserve partial work and record the next action for resumption.

Give a brief progress update after each completed iteration. At handoff, report completed/requested count and list each problem, PR URL, fresh reviewer outcome and reviewed commit, checks and limitations, and retained worktree path. Identify any unfinished iteration and the exact blocker. Stop at human PR review; leave merge and deployment decisions to the human.
