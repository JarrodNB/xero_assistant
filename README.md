# Ledger

Ledger is a financial assistant for the connected Xero demo company. Its first implemented capabilities cover contacts and sales invoices, with room for additional Xero workflows. Interviewers sign in with one shared username and password. The server talks to Xero. The chat can read supported records and propose changes, and each change runs only after its own confirmation.

Once required details are known, chat proposes the change immediately. Contact email, invoice reference, and invoice due date are optional; you can supply them in chat or edit them on the confirmation card. An omitted due date defaults to 14 days from today. The assistant asks for missing required details and can use earlier messages to resolve follow-ups such as "same contact as last".

## Run with Docker

Docker Desktop needs to be running.

```bash
copy .env.example .env
docker compose run --rm --no-deps backend python -m app.auth.hash_password --password "choose-a-password"
```

Put the printed hash in `.env` as `APP_PASSWORD_HASH`. Docker Compose treats `$` as a variable, so write each `$` in the hash as `$$`. Also set `APP_USERNAME`, `SESSION_SECRET`, `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, and `OPENAI_API_KEY`. Set `TYPESAFE_API_KEY` to screen each user message with the Jev model before the chat model runs. Jev receives the latest prompt plus at most the two immediately preceding user or assistant messages from that conversation, after personal data and secrets are protected. Historical content has a combined 4,000-character budget: the newest message is kept first, then the preceding message is kept up to the remaining budget. Jev is told to classify the latest message, using history only to resolve references, including whether the latest message adopts or continues a hazardous request. It does not grade the assistant reply. `CHAT_SUMMARY_EVERY` defaults to 10. After every further block of that many messages, older turns are folded into one summary of at most 2,000 characters that the model reuses. The chat screen still shows the full thread. Set it to 0 to turn summarization off.

Create a [Xero web app](https://developer.xero.com/documentation/guides/oauth2/auth-flow) and set its redirect URI to `http://localhost:3001/api/xero/callback`. Put the client id and client secret in `.env`. After you sign in, choose Connect Xero and authorise the Demo Company. The server stores that refresh token and reuses it for every interviewer. The connection is free for up to 25 organisations.

```bash
docker compose up --build
```

Open http://localhost:3001 and sign in with the username and password you chose. Share that pair with interviewers. Do not share the Xero client secret. The sidebar links to Invoices, Contacts, and Chat. Chat can reopen earlier conversations stored on the server. Contacts lists the demo company's names and emails.

The frontend and backend source trees are mounted into the containers. Saving a file reloads the dev server. Add a Python dependency in `backend/pyproject.toml` and rebuild the backend image. Add an npm dependency in `frontend/package.json`, then run `docker compose run --rm --no-deps frontend npm install`.

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
