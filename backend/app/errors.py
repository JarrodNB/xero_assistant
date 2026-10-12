"""Purpose: Shared API error shape for people and for the model.

Public API:
- ApiError
- tool_error
"""


class ApiError(Exception):
    """A request failed in a way the caller can act on."""

    def __init__(self, status_code: int, what: str, why: str, retryable: bool, next_step: str, *, outcome_unknown: bool = False) -> None:
        """Store the status and the explanation fields."""
        self.status_code = status_code
        self.what = what
        self.why = why
        self.retryable = retryable
        self.next_step = next_step
        self.outcome_unknown = outcome_unknown
        super().__init__(what)


def tool_error(what: str, why: str, retryable: bool, next_step: str) -> dict[str, object]:
    """Return an MCP tool failure the model can read."""
    return {
        "ok": False,
        "what": what,
        "why": why,
        "retryable": retryable,
        "next_step": next_step,
    }
