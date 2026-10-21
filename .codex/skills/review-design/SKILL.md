---
name: review-design
description: Review a code diff for architecture, maintainability, and meaningful test coverage with minimal requirements context. Use for the orchestrator's blind design review or a requested review in this scope.
---

# Design Review

Review the supplied base/head snapshot independently. Read applicable repository instructions and the installed `codebase-design` skill. Judge changes against surrounding code and actual usage, not a preferred rewrite.

## Blindness and access

- Do not read the Kanban item, plan, implementation tickets, implementation-agent reports, PR discussion, commit messages, or another reviewer's findings. Do not request intended requirements. Code, tests, schemas, and established technical documentation are available.
- If you inherited requirements or implementation rationale, report the contamination and request a fresh reviewer before this can count as blind.
- Do not modify source, tests, tickets, or workflow state. Run useful Docker checks with isolated writable test artifacts when needed. No browser automation or browser-driven tests.

## Inspect

- Interfaces that force callers to know internal sequencing/state; shallow pass-through layers; duplicated decisions spread across callers.
- Cohesion, coupling, dependency direction, and business-logic placement. Rails business logic belongs in service objects here.
- Unnecessary abstractions, speculative flexibility, and exposed internal seams. Suggest simplification only when it addresses evidenced maintenance cost.
- Tests that exercise meaningful external behavior, protect failure paths, and survive internal refactoring. Look for excessive mocking, mirrored implementation assertions, and gaps masked by green tests.
- File responsibilities, names, descriptions, and local documentation rules where they materially affect understanding or violate repository instructions.

Do not demand unrelated broad refactors. Separate optional improvements from actionable findings; preference alone is not a finding. Runtime/security analysis belongs primarily to the correctness reviewer, but report any concrete serious problem you discover.

## Report

Order actionable findings by severity: P0 urgent, P1 high, P2 normal, P3 low. Give file/line evidence, concrete maintenance/test risk, and a focused repair direction. Ground claims in actual callers/test behavior and label uncertainty.

Return reviewed base/head refs, checks actually run, and limitations. State when there are no actionable findings. A clean design review is not requirements completion or human acceptance.
