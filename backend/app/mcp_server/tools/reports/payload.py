"""Purpose: Value-free navigation and bounded protected report evidence payloads.

Public API:
- ReportHandoff
- ProtectedReportEvidence
- report_evidence
"""

from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.chat.guardrails.redaction import redact_text
from app.chat.report_facts import current_report_facts


class ReportHandoff(BaseModel):
    """Ordinary chat receives navigation only, never unvalidated report figures."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    action: Literal["open_performance"] = "open_performance"
    href: Literal["/performance"] = "/performance"
    report_type: Literal["profit_and_loss", "balance_sheet"]
    instruction: str = "Open Performance, choose dates, then Explain this change to prepare an editable report question."


class ProtectedReportEvidence(BaseModel):
    """Only bounded protected labels and evidence keys reach the typed selector."""

    schema_version: Literal["1"] = "1"
    report_type: Literal["profit_and_loss", "balance_sheet"]
    selected: str | None
    evidence: list[dict[str, str]]
    complete_calculation: bool
    other_account_details_omitted: bool


def report_evidence(report_type: Literal["profit_and_loss", "balance_sheet"]) -> ReportHandoff | ProtectedReportEvidence:
    """Reuse fresh request-local facts or explicitly hand ordinary chat to Performance."""
    facts = current_report_facts.get()
    if facts is None or facts.report.report_type != report_type:
        return ReportHandoff(report_type=report_type)
    return ProtectedReportEvidence.model_validate(facts.protected_input(redact_text))

