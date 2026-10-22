"""Purpose: Select and render source-backed report facts without model-written financial claims.

Public API:
- ReportFactSelection
- ReportFacts
- current_report_facts
"""

from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from app.reports.models import BalanceSheetComparison, ReportComparison


class ReportFactSelection(BaseModel):
    """The model chooses evidence only; all figures and sentences are application-owned."""

    model_config = ConfigDict(extra="forbid")
    evidence: list[str] = Field(default_factory=list, max_length=8)
    focus: Literal["overview", "selected", "largest_expense"] = "overview"


@dataclass
class ReportFacts:
    """One request-local trusted comparison and its context-bound account selection."""

    report: ReportComparison | BalanceSheetComparison
    selected_key: str | None
    token: str

    def default_keys(self) -> list[str]:
        """Prefer the selected account, otherwise the report metrics and largest movements."""
        return ([self.selected_key] if self.selected_key else list(self.report.metrics) + [row.key for row in self.report.top_movements[:5]])

    def allowed_keys(self) -> set[str]:
        """Expose only complete deterministic metrics and account movements as evidence."""
        return set(self.report.metrics) | {row.key for row in self.report.movements}

    def offered_keys(self) -> set[str]:
        """Limit model choices to evidence explicitly included in the bounded input."""
        keys = set(self.default_keys()) | set(self.report.metrics)
        expenses = [row for row in self.report.movements if row.category == "expenses"]
        if expenses:
            keys.add(max(expenses, key=lambda row: abs(Decimal(row.change))).key)
        return keys

    def protected_input(self, protect) -> dict:
        """Send only bounded labels, categories and direction, never report bodies or amounts."""
        keys = self.offered_keys()
        facts = [{"key": key, "label": key.replace("_", " "),
                  "direction": "increased" if Decimal(value.change) > 0 else "decreased" if Decimal(value.change) < 0 else "unchanged"}
                 for key, value in self.report.metrics.items()]
        facts.extend({"key": row.key, "label": protect(row.label), "category": row.category,
                      "direction": "increased" if Decimal(row.change) > 0 else "decreased" if Decimal(row.change) < 0 else "unchanged"}
                     for row in self.report.movements if row.key in keys)
        return {"schema_version": "1", "report_type": self.report.report_type, "selected": self.selected_key,
                "evidence": facts, "complete_calculation": True, "other_account_details_omitted": len(facts) < len(self.allowed_keys())}

    def render(self, selection: ReportFactSelection | None = None, fallback: bool = False) -> str:
        """Render exact fresh amounts and safe links, with no model-supplied prose."""
        report = self.report
        title = "Profit and loss" if isinstance(report, ReportComparison) else "Balance sheet"
        dates = (f"{report.current.date_from} to {report.current.date_to}; comparison {report.comparison.date_from} to {report.comparison.date_to}"
                 if isinstance(report, ReportComparison) else f"as at {report.current.as_of}; comparison as at {report.comparison.as_of}")
        lines = [f"{title} — {dates}. Accrual, {report.current.currency}; organisation timezone {report.current.timezone}.",
                 f"Refetched from Xero: {report.current.retrieved_at.isoformat()} and {report.comparison.retrieved_at.isoformat()}. These are separate reads, not an atomic accounting snapshot."]
        if report.status == "empty":
            return "\n".join(lines + ["At least one source has no report data. No change has been inferred."])
        keys = selection.evidence if selection and selection.evidence else self.default_keys()
        if selection and selection.focus == "largest_expense":
            expenses = [row for row in report.movements if row.category == "expenses"]
            keys = [max(expenses, key=lambda row: abs(Decimal(row.change))).key] if expenses else []
        if selection and selection.focus == "selected" and self.selected_key:
            keys = [self.selected_key]
        movements = {row.key: row for row in report.movements}
        for key in dict.fromkeys(keys):
            value = report.metrics.get(key) or movements.get(key)
            if value is None:
                raise ValueError("Unknown report evidence")
            label = movements[key].label if key in movements else key.replace("_", " ").capitalize()
            line = f"{label}: {value.current} {report.current.currency}, compared with {value.comparison} {report.current.currency}; change {value.change} {report.current.currency}."
            if key in movements and isinstance(report, ReportComparison):
                line += f" Contribution to profit change: {movements[key].contribution} {report.current.currency}."
            lines.append(line)
        if isinstance(report, ReportComparison):
            from decimal import localcontext
            with localcontext() as arithmetic:
                arithmetic.prec = 50
                displayed = sum((Decimal(movements[key].contribution) for key in dict.fromkeys(keys) if key in movements), Decimal(0))
                remainder = Decimal(report.metrics["net_profit"].change) - displayed
            lines.append(f"Profit change from all account movements not displayed above: {remainder} {report.current.currency}. This remainder excludes the summary metrics.")
        link = "/performance?" + urlencode({"context": self.token})
        lines.append(f"[View source rows (refreshes report)]({link})")
        lines.append("These figures explain the arithmetic, not the underlying business cause. The reports alone cannot establish why an account changed.")
        if not isinstance(report, ReportComparison):
            lines.append("Position changes are not profit contributions or cash flows.")
        if fallback:
            lines.append("A generated selection was unavailable; this is the verified deterministic comparison.")
        return "\n".join(lines)


current_report_facts: ContextVar[ReportFacts | None] = ContextVar("current_report_facts", default=None)
