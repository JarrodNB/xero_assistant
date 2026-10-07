# Next.js app

TypeScript and TSX files in this folder use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

The browser talks only to this Next.js app. `/api/backend` is rewritten to FastAPI. Pages call `lib/api.ts` for that API.

## Files

- `layout.tsx` — root document and metadata
- `page.tsx` — sends `/` to chat
- `globals.css` — shared styles
- `login/` — interviewer sign-in
- `(app)/` — signed-in shell, invoices, contacts, and chat
- `api/xero/` — OAuth start and callback proxies
