# Frontend library

TypeScript files here use the header comment in `frontend/AGENTS.md`. Every function has a short JSDoc description.

Shared browser and server helpers live here. Pages import these modules instead of calling FastAPI or Xero directly.

## Files

- `invoiceLimits.ts` - browser feedback for the backend's authoritative invoice numeric limits
- `api.ts` — session lookup and JSON calls through `/api/backend`
- `types.ts` — invoice, contact, conversation, and proposed-action shapes
- `xeroProxy.ts` — forward an OAuth redirect to FastAPI and keep the browser on this host
