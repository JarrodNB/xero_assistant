# Frontend regression tests

Run `npm test` through Docker Compose from Ubuntu WSL. The script compiles the API helper into `/tmp` and uses Node's built-in test runner; it needs no additional testing dependency.

JavaScript test files use the purpose/public API header from `frontend/AGENTS.md`. Describe helper functions and test cases. Mock browser storage and fetch; do not call Xero, the application server, or model providers. React interaction coverage will be added in the testing phase of the remediation plan.

## Files

- `api.test.cjs` — write receipt persistence, concurrent submissions, sanitized errors, and retry identifiers
