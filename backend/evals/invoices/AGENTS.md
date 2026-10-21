# Invoices evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`deterministic.yaml` checks which read tool ran, including contact lookup. `judge.yaml` uses each case's `LLMJudge` rubric and the dataset `G-Eval` rubric. The files can hold different cases. Both runs call the configured chat model. `scripted.py` is only for harness unit tests. This agent has no Jev screen. Jev screens the user message on the orchestrator during a live chat turn.

## Files

- `deterministic.yaml` — invoices cases and the expected read tool
- `judge.yaml` — invoices cases and rubrics
- `evaluators.py` — read-tool check
- `scripted.py` — harness stand-in for the invoices agent
- `run.py` — load one dataset and score the invoices agent

## Evaluation workflow (Phase 3)

Ordinary `pytest -q` runs offline tests and skips `live_eval` cases. Paid tests require `pytest -q --live-evals -m live_eval`; runner CLIs require `--live`, default to deterministic scoring, and support repeated `--case NAME` selections. Agent runners also support `--scoring judge`. Run through Docker Compose in Ubuntu. No production chat request runs these datasets.

Every selected case must appear exactly once with nonempty all-true assertions. Task failures and evaluator exceptions are separate failure channels and both must fail the run. Judge approval never bypasses deterministic write-claim or proposal checks. Shared validation and safe artifact handling live in `evals/reporting.py`; offline regression coverage is in `tests/test_eval_reporting.py`.

Use one deterministic case first. Concurrency is two, task deadline 90 seconds, dataset deadline 900 seconds including judging, and agent task usage is capped at 12 requests, 12 tools, and 20,000 tokens per case. Judge/Jev usage is not in that token cap; review provider billing before broad runs. Judge models use configured `MODEL`. Model aliases remain mutable; configure snapshots for comparable results.

Artifacts under `evals/artifacts/` are local and git-ignored. Retain only allowlisted metadata (versions/hashes, model identifiers, task usage, assertion booleans, latency); never persist prompts, answers, reasons, or exception bodies. Billing cost and judge/Jev usage are explicitly unavailable. Delete artifacts after 30 days; publish only reviewed summaries.

Phase 5 deterministic cases add mixed-currency totals/comparisons, empty results, and truncated reads. fixtures.py creates an isolated synthetic gateway per case using financial_scenario metadata, including a partial-empty result. FinancialAnswer checks only answer text, so correct JSON in the trace cannot hide incorrect wording. Both ExpectedRead and FinancialAnswer must pass; judge cases remain separate. Fixture cases are available through the usual opt-in --case command, with no default paid requests.
