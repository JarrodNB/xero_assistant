# Frontend regression tests

Run `npm test` through Docker Compose from Ubuntu WSL. The script compiles tested modules into `/tmp` and uses Node's built-in test runner. Form interactions use pinned Testing Library and jsdom development dependencies with the installed React version.

JavaScript test files use the purpose/public API header from `frontend/AGENTS.md`. Describe helper functions and test cases. Mock browser storage and fetch; do not call Xero, the application server, or model providers. jsdom interactions do not use the IDE browser. The broader application interaction suite remains in the testing phase of the remediation plan.

## Files

- `chatErrors.test.cjs` also verifies bounded narration for large results and the actual confirmation-to-chat transport path without private ids or diagnostics.

- `api.test.cjs` — write receipt persistence, concurrent submissions, sanitized errors, and retry identifiers
- `invoiceEdits.test.cjs` — form submissions, partial payloads, reference clearing, line removals, unsupported edits, and server-response reconciliation
- `chatErrors.test.cjs` — actual AI SDK parsing with mocked SSE errors/fetch failures, curated recovery messages, pending-card recovery, and aborting an unfinished stream. Network responses are synthetic; no browser or provider is used.
