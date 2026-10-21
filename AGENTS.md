# Ledger agent notes

Ledger is a Xero assistant for the demo company. The browser talks only to the Next.js app in `frontend`. The FastAPI service in `backend` owns sign-in, chat, invoices, and SQLite. Xero is the source of truth for contacts and invoices.

## Engineering standards

- Keep code testable, modular, focused, and simple. Prefer typed inputs and outputs, descriptive names, and existing patterns over speculative abstractions.
- Add appropriate unit, integration, or end-to-end tests for new behavior. AI functionality should have relevant evaluation cases.
- Keep documentation current, including `README.md` and `ARCHITECTURE.md` when system behavior or boundaries change.
- Every source file starts with a purpose and public API header, and every function or method has a short description. Language-specific formats are in `backend/AGENTS.md` and `frontend/AGENTS.md`.
- Every folder has an `AGENTS.md` describing its local conventions. Preserve and update these when adding folders or changing their responsibilities.
- Keep hosting costs low; avoid recurring services or infrastructure without a clear benefit.
- Do not use the IDE browser for testing; the user tests the UI locally.

## Architecture and AI engineering

- Python and PydanticAI are the default for backend AI functionality unless they are not a fit. Pin model and framework versions; do not use floating `latest` versions.
- Use typed outputs (Pydantic models) for structured LLM responses, with validation and defined behavior for validation failures. Keep model configuration such as model name, temperature, and token limits in configuration, not agent code.
- Define fallback behavior for provider outages and rate limits. Apply timeouts, bounded retries with backoff, iteration/tool-call/token limits, and a wall-clock limit to model-driven workflows. Make limit behavior explicit.
- Treat tool output and retrieved content as untrusted. Use Jev for malicious-input screening unless the task calls for otherwise, retain deterministic injection detection, validate model output before acting, and define what happens when a guardrail triggers.
- Require human confirmation for irreversible or high-impact actions. Make state-mutating tools idempotent so retries are safe.
- Define what conversation context is retained, summarized, or dropped. Check the first conversation message against a prompt cache when applicable.
- Trace model calls and AI tool use, not unrelated actions. Keep traces understandable and record useful metadata such as model, token counts, latency, cost, prompt version, and environment. Use pseudonymized session/user identifiers, track costs by use case, capture feedback when applicable, and define sampling and retention.
- Protect sensitive information across prompts, tool responses, traces, eval data, logs, and error reporting. Do not send user data to LLM providers or observability systems unless explicitly required. Send only the minimum necessary data; redact sensitive values before external processing and restore them only in the trusted application environment. Keep blocked/maskable data classes and token mapping policy centralized, including how and where mappings are stored. Test redaction and confirm provider retention/training terms.
- Version prompts and record the version used for each trace. Keep templates separate from injected values. Evaluate prompt changes before promotion and support rollback where prompts are externally managed.
- Give each use case its own offline evaluation data, including deterministic golden cases and a separate judge dataset where applicable. Test refusals and uncertainty, add regressions for incorrect conversations, and make evaluation results useful in CI. Do not run offline judge/evaluation workflows in production.
- For retrieval, use the same named/versioned embedding model for indexing and search; plan a full re-index for model changes. Define chunking, metadata, stale/deleted document removal, and deterministic golden-set evaluation. Default to hybrid search, specify and evaluate its weighting method (such as reciprocal rank fusion), and apply tenant/access filters at query time. Measure recall@k, precision@k, and MRR.
- For reranking, use a deterministic golden set, compare nDCG/MRR with the non-reranked baseline, and set candidate-count and latency budgets.
- MCP is the tool layer. Define rate and result-size limits, use consistent descriptive `verb_noun` tool names, version schemas, and test tool behavior and selection. Make empty results and truncation explicit.
- Database access must use purpose-specific tools, not arbitrary SQL from the LLM. Validate arguments, limit returned fields, resolve internal IDs when practical, and define pagination/truncation behavior.
- Tool descriptions explain when to use and not use a tool, its parameters, and one or two concise examples. Tool errors should identify the problem, retryability, and next step without exposing internals; categorize validation, not-found, permission, transient, and internal errors, suggest valid values for validation failures, return sanitized errors to the model, and log full details internally.
- Separate fast mocked-model tests from slower live evaluations. Keep CI evaluation cost bounded with a PR smoke set and larger scheduled or change-triggered runs; retain results to track trends.
- Use feature flags or gradual rollout for new prompts, models, and agent behavior where appropriate. Cache embeddings and repeated calls only when safe, and stream responses when useful to the UX. Document provider-outage and degraded-quality procedures.
- Document each AI use case's purpose, model, prompt version, tools, evaluations, and limitations. Record framework deviations and their rationale.

## Docker workflow

Install, run, and test through Docker Compose directly on Ubuntu. Do not create a host `.venv` or install project dependencies on the host. The repository path is `/home/jarrod/Desktop/xero_assistant`. Docker Engine and the Docker Compose plugin must be installed, with the daemon running and accessible to your user.

Run commands from an Ubuntu terminal, for example:

```bash
cd /home/jarrod/Desktop/xero_assistant
docker compose run --rm --build --no-deps backend pytest -q
```

- Add Python dependencies in `backend/pyproject.toml`, then rebuild with `--build`; installing a dependency in a temporary `docker compose run` container does not persist.
- `./backend/app`, `./backend/tests`, and `./backend/evals` are mounted. Uvicorn reloads when `app` changes, so those edits do not need a rebuild.
- `./frontend` is mounted and runs `next dev`; polling remains enabled for mounted-source reloads. Add npm dependencies in `frontend/package.json`, then run `docker compose run --rm --no-deps frontend npm install`.
- Run temporary Python scripts inside Docker Compose rather than on the host.
- Rebuild both images with `docker compose build`. Start the app with `docker compose up --build` from the repository directory. The site is at `http://localhost:3001` and the API at `http://localhost:8000`.
- Named volumes belong to the local Docker daemon. Image rebuilds preserve them, but moving the repository to another computer does not transfer SQLite data or installed frontend dependencies. Restore a database backup if needed; do not use `docker compose down -v` unless intentionally deleting local data.
- Compose loads `.env`. Do not print it or commit it.

## Layout

- `backend/` — API, chat agent, MCP tools, SQLite, Xero client, evals, and tests
- `frontend/` — Next.js UI, session calls, and the Xero OAuth proxy
- `AGENTS.md` files — shared and folder-specific agent instructions
- `README.md` — how to run the app
- `ARCHITECTURE.md` — request flow, the write boundary, and summarization

The orchestrator may call `propose_action` and delegate reads to the invoices subagent. That subagent may call `find_contacts`, `find_invoices`, `get_invoice`, `summarize_invoices`, and `compare_invoice_totals`. A Xero write runs after a person confirms a proposal, or when they save or void an invoice in the UI.
