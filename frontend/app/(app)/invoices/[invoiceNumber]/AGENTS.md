# Edit invoice page

TypeScript and TSX files here use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

`page.tsx` loads one invoice by the number in the route, then saves or voids it through the invoice API. The route parameter is the invoice number a person sees.

Void submission has a synchronous in-flight guard and uses the shared API helper's durable retry identifier. Never treat a lost response as proof the invoice was not voided.

Build partial updates through `lib/invoiceEdits.ts`. Untouched lines are omitted, reference clearing sends an empty string, and removed existing lines are named explicitly. Key the form to the saved server snapshot. Guard late load/save/void responses by route identity and generation; navigating away and back must not let an older response populate the current editor.
