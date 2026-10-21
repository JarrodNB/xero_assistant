---
name: review-correctness
description: Review a code diff for correctness, security, and reliability using code evidence and minimal requirements context. Use for the orchestrator's blind correctness review or a requested review in this scope.
---

# Correctness Review

Review the supplied base/head snapshot independently. Read repository instructions and trace changed behavior through code, tests, schemas, and established technical documentation. This is not requirements approval.

## Blindness and access

- Do not read the Kanban item, plan, implementation tickets, implementation-agent reports, PR discussion, commit messages, or another reviewer's findings. Do not request intended requirements. Ask for missing refs or access when needed.
- If you inherited requirements or implementation rationale, report that the review cannot count as blind and request a fresh reviewer. Ignoring known context does not remove it.
- Do not edit source, tests, tickets, or workflow state. Use isolated writable test artifacts when necessary. Run useful checks in Docker without browser automation or browser-driven tests.

## Inspect

- Incorrect outputs, invalid state transitions, regressions, error handling, and incompatible caller/schema changes.
- Authentication/authorization, tenant isolation, unsafe input handling, secret exposure, and trust boundaries.
- Transactions, races, retries, duplicate queue delivery, partial failures, and resource handling relevant to the diff.
- Repository cross-service invariants: Rails owns domain writes, long-running AI work uses queues, handlers are safe under duplicate delivery, and LLM/embedding calls follow repository rules.
- Missing tests where a concrete unprotected behavior creates credible bug risk. Do not invent product requirements.

Trace suspected defects to a concrete input or execution path. Inspect surrounding code before reporting. Focus on problems introduced or materially worsened by the diff; distinguish demonstrated failures from inference.

## Report

Order actionable findings by severity: P0 urgent, P1 high, P2 normal, P3 low. Each must include file/line evidence, the trigger and supported failure, user/system impact, and a focused repair direction. Prefer a changed-code location. Include reproduction/test evidence or label the finding as code inference.

Return reviewed base/head refs, checks actually run, and limitations. State when there are no actionable defects. Do not claim requirements completion or unrun tests passing.
