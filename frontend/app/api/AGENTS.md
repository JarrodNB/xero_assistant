# Next.js route handlers

TypeScript files under `api/` use the header comment in `frontend/AGENTS.md`. Every function has a short JSDoc description.

Route handlers in this tree proxy browser calls that must stay on the Next.js origin. Application JSON stays on the `/api/backend` rewrite in `next.config.ts`. The Xero OAuth redirects live in `xero/`.
