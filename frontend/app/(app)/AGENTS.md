# Signed-in shell

TypeScript and TSX files here use the header comment in `frontend/AGENTS.md`. Every function and component has a short JSDoc description.

`layout.tsx` is the sidebar shell for invoices, contacts, and chat. It reads the session and sends a missing session to login. Child routes assume that shell.

## Routes

- `invoices/` — invoice list
- `invoices/new/` — create an invoice in the UI
- `invoices/[invoiceNumber]/` — edit or void one invoice
- `contacts/` — demo-company names and emails
- `chat/` — conversation list and the chat panel
- `performance/` — read-only accounting reports with explicit source rows and metadata
