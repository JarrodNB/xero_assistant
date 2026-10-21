# Orchestrator evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`deterministic.yaml` checks delegation, `propose_action`, and unconfirmed write claims. `judge.yaml` uses each case's `LLMJudge` rubric and the dataset `G-Eval` rubric. The files can hold different cases. Both runs call the configured chat model. The scored gateway already contains Bob's Construction, so a complete invoice proposal does not create the contact first. `scripted.py` is only for harness unit tests. Jev is the live input filter in `backend/app/chat`, not an evaluator here.

Optional-field regressions cover omitted and partially supplied invoice fields, required-detail clarification, contact email, and a same-contact follow-up. Conversation inputs use `prompt` and `previous_messages` with `role` and `content`; prior turns become actual model history. Scored answers and tool traces are protected, and the tool trace contains only the current turn. Live runs have bounded usage and a per-case timeout. Assert evaluation results are true, rather than only checking that assertion dictionaries exist.

Judge scoring must also verify proposal facts mechanically when a case expects a proposal. A judge's approval cannot replace evidence of one successful pending action in the current turn. Repeated live regressions exercise contact-name protection across lookup and later model requests.

## Files

Bounded-confirmation golden and judge cases cover executed outcomes with sparse facts and unknown outcomes that must not claim success/failure or propose replay. Live runs remain opt-in; offline schema checks are not live prompt-quality evidence.

PendingProposalEvidence validates successful pending tool evidence, matching operation, and a structured payload without requiring receipt ids. Provider history and resulting evaluation traces omit those private ids; durable receipt creation and UI routing are covered by deterministic integration tests.

- `deterministic.yaml` — orchestrator cases and delegate metadata
- `judge.yaml` — orchestrator cases and rubrics
- `evaluators.py` — delegation and proposal checks
- `scripted.py` — parent harness script; child reads use the invoices stand-in
- `run.py` — load one dataset and score the orchestrator

## Evaluation workflow (Phase 3)

Ordinary `pytest -q` runs offline tests and skips `live_eval` cases. Paid tests require `pytest -q --live-evals -m live_eval`; runner CLIs require `--live`, default to deterministic scoring, and support repeated `--case NAME` selections. Agent runners also support `--scoring judge`. Run through Docker Compose in Ubuntu. No production chat request runs these datasets.

Every selected case must appear exactly once with nonempty all-true assertions. Task failures and evaluator exceptions are separate failure channels and both must fail the run. Judge approval never bypasses deterministic write-claim or proposal checks. Shared validation and safe artifact handling live in `evals/reporting.py`; offline regression coverage is in `tests/test_eval_reporting.py`.

Use one deterministic case first. Concurrency is two, task deadline 90 seconds, dataset deadline 900 seconds including judging, and agent task usage is capped at 12 requests, 12 tools, and 20,000 tokens per case. Judge/Jev usage is not in that token cap; review provider billing before broad runs. Judge models use configured `MODEL`. Model aliases remain mutable; configure snapshots for comparable results.

Artifacts under `evals/artifacts/` are local and git-ignored. Retain only allowlisted metadata (versions/hashes, model identifiers, task usage, assertion booleans, latency); never persist prompts, answers, reasons, or exception bodies. Billing cost and judge/Jev usage are explicitly unavailable. Delete artifacts after 30 days; publish only reviewed summaries.
