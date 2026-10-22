"""Purpose: Typed source-backed accounting report results.

Public API:
- ReportRow
- FinancialReport
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportRow(BaseModel):
    """One visible source row, with private identity retained for comparisons only."""

    model_config = ConfigDict(extra="forbid")
    key: str
    kind: Literal["section", "account", "summary"]
    label: str
    amount: str | None = None
    children: list["ReportRow"] = Field(default_factory=list)
    account_id: str | None = Field(default=None, exclude=True)


class FinancialReport(BaseModel):
    """A complete validated report in the organisation's base currency."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    report_type: Literal["profit_and_loss"] = "profit_and_loss"
    status: Literal["ready", "empty"]
    complete: Literal[True] = True
    date_from: date
    date_to: date
    basis: Literal["accrual"] = "accrual"
    currency: str
    currency_decimal_places: int
    timezone: str
    retrieved_at: datetime
    rows: list[ReportRow]
