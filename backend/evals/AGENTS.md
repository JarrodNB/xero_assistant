# Evals

Python files here use the module docstring in `backend/AGENTS.md`. Every function and method has a one-line docstring.

The orchestrator and the invoices agent each have a deterministic dataset and a judge dataset. The two files can hold different cases. Both runs call the configured chat model. Deterministic scoring compares the answer and tool trace with the case expectations. Judge scoring sends the answer to a judge model with that case's rubric. Jev scores are grouped by use under `jev/`. The user-message screen is the one scored use so far. Its inputs may include bounded prior messages, and its runner uses the production PII/secret protection and context formatter before calling Jev. That run compares the strict-policy action with the expected action. A chat request does none of these.

```bash
python -m evals.orchestrator.run
python -m evals.invoices.run
python -m evals.jev.user_message.run
```

Dataset cases must not contain passwords, tokens, or other secrets. Invoice fields a case needs can stay.

## Files

- `checks.py` — shared write-claim check
- `scoring.py` — names for the deterministic dataset and the judge dataset
- `trace.py` — answer text and the appended tool trace
- `turn.py` — run one prompt on the fake invoice gateway

## Packages

- `orchestrator/` — golden cases for delegation and `propose_action`
- `invoices/` — golden cases for contact and invoice reads
- `jev/` — Jev scores, one package per use. `user_message/` is the strict-policy screen of the user message
