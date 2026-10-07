# Invoices evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`deterministic.yaml` checks which read tool ran, including contact lookup. `judge.yaml` uses each case's `LLMJudge` rubric and the dataset `G-Eval` rubric. The files can hold different cases. Both runs call the configured chat model. `scripted.py` is only for harness unit tests. This agent has no Jev screen. Jev screens the user message on the orchestrator during a live chat turn.

## Files

- `deterministic.yaml` — invoices cases and the expected read tool
- `judge.yaml` — invoices cases and rubrics
- `evaluators.py` — read-tool check
- `scripted.py` — harness stand-in for the invoices agent
- `run.py` — load one dataset and score the invoices agent
