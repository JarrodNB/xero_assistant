# UI components

TypeScript and TSX files here use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

Components in this folder are shared by more than one route. A component used by a single page can stay next to that page until a second route needs it.

Invoice submission has a synchronous in-flight guard. Chat cards use the stored receipt status after an error and offer read-only status checks for executing/unknown actions. A lost HTTP response must never be displayed as proof that an external write failed.

An invoice edit validates line values only when lines changed. Unsupported existing lines must not block metadata changes. Disable unsupported line edits and amount edits with explicit tax; explain the available alternatives in the form. Disable fields during saving so a keyed remount from the saved server response cannot discard edits made while saving.

## Files

- `ChatPanel.tsx` — one conversation, streaming replies, and confirm or deny cards
- `InvoiceForm.tsx` — line items and the save and void actions used by the invoice editor
Chat SDK error/cancellation states must release the composer and text-pacing locks. Render curated guidance for known backend errors, never arbitrary exception text. Keep pending proposal cards recoverable and offer Stop reply while a request is busy. Do not automatically retry interrupted turns or narrations.
