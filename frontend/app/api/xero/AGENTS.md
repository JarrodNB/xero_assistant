# Xero OAuth proxy

TypeScript files here use the header comment in `frontend/AGENTS.md`. Every function has a short JSDoc description.

These routes keep the Xero redirect on the Next.js origin and forward it to FastAPI. They do not store the client secret or tokens. Shared redirect handling is `lib/xeroProxy.ts`.

## Routes

- `start/` — begin the authorisation-code flow
- `callback/` — finish the flow and return the browser to the app
