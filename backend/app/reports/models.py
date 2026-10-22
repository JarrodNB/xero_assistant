"""Purpose: Typed source-backed accounting report results.

Public API:
- ReportRow
- FinancialReport
- AmountComparison
- AccountMovement
- ReportComparison
- BalanceSheetReport
- PositionMovement
- BalanceSheetComparison
- BalanceSheetQuery
- ProfitAndLossQuery
- ProfitComparisonQuery
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


class ProfitAndLossQuery(BaseModel):
    """Only explicit period-range fields are valid for a P&L report."""

    model_config = ConfigDict(extra="forbid")
    date_from: date | None = None
    date_to: date | None = None


class ProfitComparisonQuery(ProfitAndLossQuery):
    """Typed current and comparative P&L ranges with deliberate date presets."""

    comparison_from: date | None = None
    comparison_to: date | None = None
    preset: Literal["previous_period", "previous_year", "custom"] = "previous_period"


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


class AmountComparison(BaseModel):
    """Exact current/baseline figures and a meaningful percentage when available."""

    current: str
    comparison: str
    change: str
    percentage_change: str | None
    percentage_note: str | None = None


class AccountMovement(AmountComparison):
    """An aligned account change with request-local source references."""

    key: str
    label: str
    previous_label: str | None = None
    category: Literal["income", "expenses"]
    contribution: str
    current_source: str | None
    comparison_source: str | None
    account_id: str = Field(exclude=True)


class ReportComparison(BaseModel):
    """A complete pair of reports and reconciled deterministic movements."""

    schema_version: Literal["1"] = "1"
    report_type: Literal["profit_and_loss"] = "profit_and_loss"
    status: Literal["ready", "empty"]
    complete: Literal[True] = True
    current: FinancialReport
    comparison: FinancialReport
    metrics: dict[str, AmountComparison] = Field(default_factory=dict)
    movements: list[AccountMovement] = Field(default_factory=list)
    top_movements: list[AccountMovement] = Field(default_factory=list)
    other_movements: str | None = None
    warnings: list[str] = Field(default_factory=list)


class BalanceSheetReport(BaseModel):
    """A validated accrual position at one date, never a date-range flow."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1"] = "1"
    report_type: Literal["balance_sheet"] = "balance_sheet"
    status: Literal["ready", "empty"]
    complete: Literal[True] = True
    as_of: date
    basis: Literal["accrual"] = "accrual"
    currency: str
    currency_decimal_places: int
    timezone: str
    retrieved_at: datetime
    rows: list[ReportRow]


class BalanceSheetQuery(BaseModel):
    """Only as-of inputs are valid for the position report interface."""

    model_config = ConfigDict(extra="forbid")
    as_of: date | None = None
    comparison_as_of: date | None = None
    preset: Literal["previous_month", "previous_year", "custom"] = "previous_month"


class PositionMovement(AmountComparison):
    """An account position change within assets, liabilities or equity."""

    key: str
    label: str
    previous_label: str | None = None
    category: Literal["assets", "liabilities", "equity"]
    section: str
    current_source: str | None
    comparison_source: str | None
    account_id: str = Field(exclude=True)


class BalanceSheetComparison(BaseModel):
    """Two validated positions with category-preserving account deltas."""

    schema_version: Literal["1"] = "1"
    report_type: Literal["balance_sheet"] = "balance_sheet"
    status: Literal["ready", "empty"]
    complete: Literal[True] = True
    current: BalanceSheetReport
    comparison: BalanceSheetReport
    metrics: dict[str, AmountComparison] = Field(default_factory=dict)
    movements: list[PositionMovement] = Field(default_factory=list)
    top_movements: list[PositionMovement] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
