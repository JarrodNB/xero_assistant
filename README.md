# Ledger

A Xero assistant for the demo company. The current domains are contacts and invoices. Interviewers sign in with one shared username and password. The server talks to Xero. The chat can read those records and propose changes, and each change runs only after its own confirmation.

## Run with Docker

Docker Desktop needs to be running.

```bash
copy .env.example .env
docker compose run --rm --no-deps backend python -m app.auth.hash_password --password "choose-a-password"
```

Put the printed hash in `.env` as `APP_PASSWORD_HASH`. Docker Compose treats `$` as a variable, so write each `$` in the hash as `$$`. Also set `APP_USERNAME`, `SESSION_SECRET`, `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, and `OPENAI_API_KEY`. Set `TYPESAFE_API_KEY` to screen each user message with the Jev model before the chat model runs. Jev does not grade the assistant reply. `CHAT_SUMMARY_EVERY` defaults to 10. After every further block of that many messages, older turns are folded into a summary the model reuses. The chat screen still shows the full thread. Set it to 0 to turn summarization off.

Create a [Xero web app](https://developer.xero.com/documentation/guides/oauth2/auth-flow) and set its redirect URI to `http://localhost:3000/api/xero/callback`. Put the client id and client secret in `.env`. After you sign in, choose Connect Xero and authorise the Demo Company. The server stores that refresh token and reuses it for every interviewer. The connection is free for up to 25 organisations.

```bash
docker compose up --build
```

Open http://localhost:3000 and sign in with the username and password you chose. Share that pair with interviewers. Do not share the Xero client secret. The sidebar links to Invoices, Contacts, and Chat. Chat can reopen earlier conversations stored on the server. Contacts lists the demo company's names and emails.

The frontend and backend source trees are mounted into the containers. Saving a file reloads the dev server. Add a Python dependency in `backend/pyproject.toml` and rebuild the backend image. Add an npm dependency in `frontend/package.json`, then run `docker compose run --rm --no-deps frontend npm install`.

## Tests

```bash
docker compose run --rm --build --no-deps backend pytest
```

The golden dataset is `backend/evals/invoice_golden.yaml`. Pytest loads it and runs the deterministic checks with a scripted model. That judge is not the chat guardrail. Jev screens the user message on a live chat turn when `TYPESAFE_API_KEY` is set. To score the dataset with its LLM judge and G-Eval rubric:

```bash
docker compose run --rm --no-deps backend python -m evals.run_invoice_evals
```

## Optional traces

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` to send the Jev screen and chat generations to Langfuse Cloud. HTTP request spans are not sent. Invoice fields the model needs can appear in those traces. Passwords, the Xero client secret, and access tokens are redacted and are not instrumented from the Xero HTTP client.
