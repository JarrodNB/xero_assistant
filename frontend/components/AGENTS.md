# UI components

TypeScript and TSX files here use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

Components in this folder are shared by more than one route. A component used by a single page can stay next to that page until a second route needs it.

Invoice submission has a synchronous in-flight guard. Chat cards use the stored receipt status after an error and offer read-only status checks for executing/unknown actions. A lost HTTP response must never be displayed as proof that an external write failed.

## Files

- `ChatPanel.tsx` — one conversation, streaming replies, and confirm or deny cards
- `InvoiceForm.tsx` — line items and the save and void actions used by the invoice editor
