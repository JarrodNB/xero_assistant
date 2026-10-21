# Evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

The orchestrator and the invoices agent each have a deterministic dataset and a judge dataset. The two files can hold different cases. Both runs call the configured chat model. Deterministic scoring compares the answer and tool trace with the case expectations. Judge scoring sends the answer to a judge model with that case's rubric. Jev scores are grouped by use under `jev/`. The user-message screen is the one scored use so far. Its inputs may include bounded prior messages, and its runner uses the production PII/secret protection and context formatter before calling Jev. That run compares the strict-policy action with the expected action. A chat request does none of these.

```bash
python -m evals.orchestrator.run --live --scoring deterministic --case unpaid_total
python -m evals.invoices.run --live --scoring deterministic --case unpaid_total
python -m evals.jev.user_message.run --live --case unpaid_total
```

Dataset cases must not contain passwords, tokens, or other secrets. Invoice fields a case needs can stay.

## Files

- `checks.py` — shared write-claim check
- `scoring.py` — names for the deterministic dataset and the judge dataset
- `trace.py` — answer text and the appended tool trace
- `turn.py` — run a string prompt or typed conversation input on the fake invoice gateway; protect the latest prompt and prior user/assistant messages with one request-scoped vault, and enforce model usage limits

## Packages

- `orchestrator/` — golden cases for delegation and `propose_action`
- `invoices/` — golden cases for contact and invoice reads
- `jev/` — Jev scores, one package per use. `user_message/` is the strict-policy screen of the user message

## Evaluation workflow (Phase 3)

Ordinary `pytest -q` runs offline tests and skips `live_eval` cases. Paid tests require `pytest -q --live-evals -m live_eval`; runner CLIs require `--live`, default to deterministic scoring, and support repeated `--case NAME` selections. Agent runners also support `--scoring judge`. Run through Docker Compose in Ubuntu. No production chat request runs these datasets.

Every selected case must appear exactly once with nonempty all-true assertions. Task failures and evaluator exceptions are separate failure channels and both must fail the run. Judge approval never bypasses deterministic write-claim or proposal checks. Shared validation and safe artifact handling live in `evals/reporting.py`; offline regression coverage is in `tests/test_eval_reporting.py`.

Use one deterministic case first. Concurrency is two, task deadline 90 seconds, dataset deadline 900 seconds including judging, and agent task usage is capped at 12 requests, 12 tools, and 20,000 tokens per case. Judge/Jev usage is not in that token cap; review provider billing before broad runs. Judge models use configured `MODEL`. Model aliases remain mutable; configure snapshots for comparable results.

Artifacts under `evals/artifacts/` are local and git-ignored. Retain only allowlisted metadata (versions/hashes, model identifiers, task usage, assertion booleans, latency); never persist prompts, answers, reasons, or exception bodies. Billing cost and judge/Jev usage are explicitly unavailable. Delete artifacts after 30 days; publish only reviewed summaries.
