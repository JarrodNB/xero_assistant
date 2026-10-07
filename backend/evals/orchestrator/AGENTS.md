# Orchestrator evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`deterministic.yaml` checks delegation, `propose_action`, and unconfirmed write claims. `judge.yaml` uses each case's `LLMJudge` rubric and the dataset `G-Eval` rubric. The files can hold different cases. Both runs call the configured chat model. The scored gateway already contains Bob's Construction, so a complete invoice proposal does not create the contact first. `scripted.py` is only for harness unit tests. Jev is the live input filter in `backend/app/chat`, not an evaluator here.

## Files

- `deterministic.yaml` — orchestrator cases and delegate metadata
- `judge.yaml` — orchestrator cases and rubrics
- `evaluators.py` — delegation and proposal checks
- `scripted.py` — parent harness script; child reads use the invoices stand-in
- `run.py` — load one dataset and score the orchestrator
