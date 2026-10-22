# Chat guardrails

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`__init__.py` only composes the input chain and the tool guard. Presidio placeholders live in `pii.py`. `redaction.py` applies that vault to prompts and tool calls, and still strips API keys. `context.py` protects and formats the latest prompt with at most two protected preceding user or assistant messages from the same request. Historical content has a combined 4,000-character budget, allocated newest message first, then the beginning of the older message up to the remainder. The formatter tells Jev to classify the latest message, use history only to resolve references, and treat adoption or continuation of a historical hazard as hazardous. The strict input policy, its thresholds, and the user-message screen live in `policy_screen.py`. That screen currently calls Jev. Known phrases run before it. It does not see the new assistant reply or the child brief. The user-message cases live in `backend/evals/jev/user_message/`.

The vault reuses already known raw values before fresh detection, with boundaries that keep distinct names distinct. Model history protection runs before every parent and child model request on copies, including structured tool arguments and results. Existing placeholders stay unchanged; mappings remain request-scoped and are used only in the trusted application to restore tool arguments and outgoing replies.

## Files

Provider-history copies remove action_id, line_item_id, and removed_line_item_ids recursively from structured tool results. Preserve the trusted originals so browser events can still route confirmation cards. Chat updates resolve accounting identities deterministically, never through a model.

- `__init__.py` — wire protection, secret redaction, the known-phrase screen, and the policy screen into `chat_guardrails`
- `context.py` — protect, type, bound, and format request-scoped conversation context for Jev
- `pii.py` — Presidio vault, numbered placeholders, and restoring the outbound stream. A person hit that is only an invoice field label, such as a reference, is left as written.
- `redaction.py` — protect prompts and tool results, restore tool arguments, and strip secrets
- `phrase_screen.py` — known jailbreak, harm, dosage, and self-harm phrases
- `policy_screen.py` — strict input policy, refusal routes, and the user-message screen
Configured Jev screening is bounded by `JEV_TIMEOUT_SECONDS` (five by default) and the overall chat deadline. Failure remains fail-closed; cancellation must propagate and request context must reset. Do not send failed-screen diagnostics or raw content to traces. Guardrail tracing is metadata only.

`redact_text` first removes the known application-rendered report envelope via report_history; ordinary model inputs, summaries and Jev history must not ingest report figures. The isolated report workflow screens protected labels separately with the pinned report Jev setting and metadata-only guard tracing. Failed configured screening selects deterministic rendering, and narration disabled performs no report provider/screener work.
