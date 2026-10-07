# Xero OAuth callback

TypeScript files here use the header comment in `frontend/AGENTS.md`. Every function has a short JSDoc description.

`route.ts` exports `GET`, which proxies the Xero redirect back to FastAPI through `proxyXeroRedirect`. The Xero app's redirect URI is this path on the Next.js origin.
