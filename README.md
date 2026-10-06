# Ledger

An invoice assistant for Xero's demo company. Interviewers sign in with one shared username and password. The server talks to Xero. The chat can read invoices and propose changes, and each change runs only after its own confirmation.

## Run with Docker

Docker Desktop needs to be running.

```bash
copy .env.example .env
docker compose run --rm --no-deps backend python -m app.auth.hash_password --password "choose-a-password"
```

Put the printed hash in `.env` as `APP_PASSWORD_HASH`. Docker Compose treats `$` as a variable, so write each `$` in the hash as `$$`. Also set `APP_USERNAME`, `SESSION_SECRET`, `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, and `OPENAI_API_KEY`. Set `TYPESAFE_API_KEY` to screen each user message with the Jev model before the chat model runs. Jev does not grade the assistant reply.

Create a [Xero custom connection](https://developer.xero.com/custom-development), authorise it to the Demo Company, and grant `accounting.invoices`, `accounting.contacts`, and `accounting.settings`. The connection is free while it points at the demo company.

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in with the username and password you chose. Share that pair with interviewers. Do not share the Xero client secret.

## Tests

```bash
docker compose run --rm --build --no-deps backend pytest
```

The golden dataset is `backend/evals/invoice_golden.yaml`. Pytest loads it and runs the deterministic checks with a scripted model. That judge is not the chat guardrail. Jev screens the user message on a live chat turn when `TYPESAFE_API_KEY` is set. To score the dataset with its LLM judge and G-Eval rubric:

```bash
docker compose run --rm --no-deps backend python -m evals.run_invoice_evals
```

## Optional traces

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to send agent traces to Langfuse Cloud. Invoice fields the model needs can appear in those traces. Passwords, the Xero client secret, and access tokens are redacted and are not instrumented from the Xero HTTP client.
