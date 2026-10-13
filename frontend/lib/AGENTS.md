# Frontend library

TypeScript files here use the header comment in `frontend/AGENTS.md`. Every function has a short JSDoc description.

Shared browser and server helpers live here. Pages import these modules instead of calling FastAPI or Xero directly.

`api.ts` retains an editor write UUID in tab-scoped session storage while its outcome is uncertain. Storage contains only a request fingerprint and UUID, never the raw body. Retrying identical values checks the same durable receipt; known success or rejection releases the browser id. Do not add automatic retries of confirmations or start a new id after an uncertain result.

## Files

- `actionNarration.ts` — bounded confirmation/denial outcome facts, excluding ids, line lists, references, and error diagnostics. Keep narration within the minimum supported 256-character chat prompt budget.

- `invoiceEdits.ts` — partial update payloads, intentional reference clearing, line identity/removal tracking, and due-date clearing validation

- `invoiceLimits.ts` - browser feedback for the backend's authoritative invoice numeric limits
- `api.ts` — session lookup and JSON calls through `/api/backend`
- `types.ts` — invoice, contact, conversation, and proposed-action shapes
- `xeroProxy.ts` — forward an OAuth redirect to FastAPI and keep the browser on this host
