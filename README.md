# Ledger

### A conversational assistant for Xero

Ledger lets you ask questions about a company's invoices and turn a request into a change you can review before it reaches Xero. It combines a chat interface with contact browsing and an invoice editor, using Xero's Demo Company for real API integration.

I built this project to explore a practical question: **how do you give an AI assistant useful access to financial software while keeping people in control of changes?**

## What you can do

- Ask which invoices are overdue, check unpaid totals, or compare invoice totals across two periods.
- Find a customer or inspect an invoice without navigating Xero manually.
- Request a new contact or create, update, or void an invoice through chat. Ledger presents a confirmation card before executing each action.
- Review and edit invoices directly in the UI.
- Reopen saved conversations and continue with requests such as “use the same contact.”

For example, **“Create an invoice for Bob's Construction for $200 of consulting”** starts with a contact lookup. Once the required details are available, Ledger presents the proposed invoice. You can add a reference or change the due date on the card, then confirm it. If the contact doesn't exist, creating that contact requires its own confirmation first.

## Engineering decisions

**Keep the write boundary in application code.** The model can look up records and propose an action, but it cannot execute a Xero write. FastAPI validates the proposal and handles execution after a person confirms it. The invoice editor uses the same service and validation rules.

**Give agents focused responsibilities.** A PydanticAI orchestrator handles the conversation and proposals. A separate agent handles contact and invoice reads through purpose-specific MCP tools. Neither needs arbitrary database access.

**Treat money as decimal data.** The backend validates quantities, unit prices, and totals with explicit precision and size limits. Decimal values are sent to Xero as strings to avoid rounding introduced by binary floating point.

**Protect data before model calls.** Personal values are replaced with placeholders in prompts, conversation history, and tool results, then restored inside the application. Secrets are masked separately. Deterministic checks and optional Jev screening address malicious input; regression cases include instructions hidden in contact notes.

**Keep the infrastructure small.** Next.js and FastAPI run in two Docker containers. SQLite stores conversations and pending actions; Xero remains the source of truth for contacts and invoices. Older conversation turns are summarized to limit the context sent to the model.

## Stack and architecture

| Layer | Technology |
| --- | --- |
| Interface | Next.js, React, TypeScript |
| API and validation | FastAPI, Pydantic |
| AI and tools | PydanticAI, MCP, OpenAI; optional Jev screening |
| Integration | Xero API, OAuth 2.0 |
| Persistence | SQLite, SQLAlchemy |
| Development and testing | Docker Compose, pytest, Pydantic Evals |
| Optional model tracing | Langfuse |

The browser communicates with Next.js, which proxies API requests to FastAPI. The backend owns authentication, agent execution, persistence, and Xero access.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request flow and confirmation sequence.

## Testing the assistant

The tests cover authentication, action confirmation, invoice validation, Xero OAuth, conversation state, and data redaction. Agent evaluations exercise both individual requests and follow-up conversations.

Evaluation cases include ambiguous or missing details, optional invoice fields, denied actions, prompt injection, and attempts to claim an unconfirmed write succeeded. Deterministic checks inspect tool calls and results alongside model-based judging. A judge's approval alone cannot pass a case that required a proposal the agent never made.

The datasets and evaluation runners are in [backend/evals](backend/evals); API and regression tests are in [backend/tests](backend/tests). Live model evaluations require provider credentials and incur API usage costs.

## Run locally

The project uses Docker Compose. Configure a local `.env` using [.env.example](.env.example); a connected demo needs Xero OAuth credentials and an OpenAI API key.

```bash
docker compose up --build
```

Open [localhost:3001](http://localhost:3001). The backend runs on port 8000.

To run the backend suite, including live evaluation cases:

```bash
docker compose run --rm --build --no-deps backend pytest
```

## Project scope

Ledger is a portfolio project built around one connected Xero Demo Company and shared demo sign-in. Its implemented workflows cover contacts and sales invoices. Production multi-tenant access, broader accounting workflows, and production deployment are outside the current scope.
