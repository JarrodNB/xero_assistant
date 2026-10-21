# Invoice list

TypeScript and TSX files here use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

`page.tsx` lists invoices from the API and links to create or open one. Creating and editing use `components/InvoiceForm.tsx` on the child routes.

List summaries render amounts per currency with their codes; empty groups render no matching invoices without assuming currency. Keep partial lists visible with recovery guidance when the summary rejects truncation. Clear old results on filter changes and ignore late responses; never show absence before a complete list loads. invoiceList.test.cjs covers these interactions.
