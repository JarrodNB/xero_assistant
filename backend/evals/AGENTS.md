# Invoice evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

`invoice_golden.yaml` is the golden dataset. Each case has an LLM-as-a-judge rubric, and the dataset also carries a G-Eval rubric. Pytest runs the shared deterministic checks offline. The model judges run only from `python -m evals.run_invoice_evals` when `OPENAI_API_KEY` is a real key.

Dataset cases and judge prompts must not contain passwords, tokens, or other secrets. Invoice fields the case needs can stay.

## Files

- `invoice_golden.yaml` — cases, per-case rubrics, and the G-Eval rubric
- `evaluators.py` — shared deterministic checks, including the unconfirmed-write check
- `run_invoice_evals.py` — load the dataset and score the chat agent
