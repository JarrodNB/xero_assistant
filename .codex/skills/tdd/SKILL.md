---
name: tdd
description: Implement or fix behavior through small red-green-refactor cycles at observable interfaces. Use for approved implementation tickets or when the user requests test-driven development.
---

# TDD

Read applicable repository instructions and existing tests. Implement approved behavior one observable outcome at a time through a real interface, using existing test seams and conventions. Do not add abstractions just to make mocking convenient.

## Red → green → refactor

1. Choose the smallest meaningful acceptance behavior and write one focused test for its expected outcome.
2. Run the test and observe failure for the intended missing behavior. Syntax errors, missing dependencies, unavailable databases, and broken test setup are not red: fix setup first. If behavior already passes, inspect why and choose an uncovered requirement; do not manufacture failure.
3. Make the smallest production change that satisfies the test, then observe green.
4. Refactor when it improves the code, keeping relevant tests green. Repeat for the next behavior. Do not write a speculative suite first or implement the entire ticket before checking the first failure.
5. Run relevant broader checks once complete. Verify the behavior through necessary layers and meaningful failure paths.

## Test quality and execution

- Assert observable results, errors, persisted state, or emitted work. Avoid private-method assertions, incidental call ordering, and implementation-mirroring tests.
- Stub true external services at their seam; prefer real local collaborators or established test substitutes when practical. Do not mock away the business behavior under test.
- For bug fixes, add regression coverage. For changed queue behavior, exercise duplicate delivery where it could affect idempotency.
- Follow Docker execution rules. Use non-browser tests only: no browser automation, browser-driven end-to-end tests, or browser QA. Report visual/manual checks for the human.
- Documentation, metadata, and purely mechanical edits do not need artificial red tests. Use appropriate static/existing checks and explain the exception; follow more specific repository requirements.
- Report actual commands/results, including the intended red failure and green result. If execution is blocked, say so. Written tests alone are not passing-test evidence.

## Delegated tickets

Stay within the assigned worktree/branch and approved scope. Respect blockers and report material ambiguity to the orchestrator. Do not change the board, publish tickets, open PRs, merge, or deploy. Return changed files/commits, acceptance outcomes, verification evidence, and concerns. The orchestrator owns integration and ticket status.
