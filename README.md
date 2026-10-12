# Ledger

Ledger is a financial assistant for the connected Xero demo company. Its first implemented capabilities cover contacts and sales invoices, with room for additional Xero workflows. Interviewers sign in with one shared username and password. The server talks to Xero. The chat can read supported records and propose changes, and each change runs only after its own confirmation.

Once required details are known, chat proposes the change immediately. Contact email, invoice reference, and invoice due date are optional; you can supply them in chat or edit them on the confirmation card. An omitted due date defaults to 14 days from today. The assistant asks for missing required details and can use earlier messages to resolve follow-ups such as "same contact as last".

## Development

Ledger uses a Next.js frontend, a FastAPI backend, and SQLite. Xero is the source of truth for contacts and invoices. See [ARCHITECTURE.md](ARCHITECTURE.md) for the request flow and confirmation boundary.

The application runs through Docker Compose. Configuration variables are listed in [.env.example](.env.example).

```bash
docker compose up --build
```

The frontend is available at http://localhost:3001 and the API at http://localhost:8000. Source trees are mounted into the containers for development reloads.

## Tests

```bash
docker compose run --rm --build --no-deps backend pytest
```

Pytest scores a deterministic dataset and a judge dataset for the orchestrator, and the same pair for the invoices agent. The files are `deterministic.yaml` and `judge.yaml` in `backend/evals/orchestrator/` and `backend/evals/invoices/`. A case can live in one file. Both runs call the configured chat model. Deterministic scoring compares the answer and tool trace with the case expectations. Judge scoring sends the answer to a judge model with that case's rubric. Jev scores live under `backend/evals/jev/`, one package per use. The user-message screen is `user_message/deterministic.yaml`. That score calls the configured Jev model and compares the strict-policy action with the expected action. There is no judge for that screen. The same scores run from:

```bash
docker compose run --rm --no-deps backend python -m evals.orchestrator.run
docker compose run --rm --no-deps backend python -m evals.invoices.run
docker compose run --rm --no-deps backend python -m evals.jev.user_message.run
```

Jev also screens the protected latest user message with its bounded two-message conversation tail on a live chat turn when `TYPESAFE_API_KEY` is set. The chat request does not call a judge.

The orchestrator cases include optional-field defaults, partially supplied fields, required-detail clarification, and a same-contact follow-up with actual message history. Conversation cases provide `prompt` and `previous_messages` (`role`, `content`). The eval protects both with one request-scoped vault before the model receives them, and its tool trace includes only the new turn.

Before each parent and child model request, Ledger protects a copy of model history again using the turn's known personal values. This keeps contact names consistent when detection differs between a sentence and a lookup result. Judge evaluation also checks expected pending proposals mechanically; a judge approval alone cannot prove an action was proposed.

## Optional traces

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to send the Jev screen and chat generations to Langfuse Cloud. HTTP request spans are not sent. Invoice amounts can appear in those traces. Personal data is replaced with placeholders before it reaches the model. Passwords, the Xero client secret, and access tokens are redacted and are not instrumented from the Xero HTTP client.
