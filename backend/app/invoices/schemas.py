"""Purpose: Versioned JSON contracts for invoice reads, native totals and tool errors.

Public API:
- InvoiceListPayload, InvoiceSummaryPayload, PeriodComparisonPayload, ToolErrorPayload
"""

from typing import Literal
from typing_extensions import TypedDict


class InvoiceListPayload(TypedDict):
    """A bounded v2 invoice list with explicit completeness and recovery guidance."""

    schema_version: Literal["2"]
    complete: bool
    scanned_count: int
    limit: int
    next_step: str | None
    invoices: list[dict[str, object]]


class CurrencySummaryPayload(TypedDict):
    """Counts and monetary totals in one native currency."""

    currency: str
    invoice_count: int
    unpaid_count: int
    overdue_count: int
    unpaid_total: float
    overdue_total: float
    invoice_total: float


class InvoiceSummaryPayload(TypedDict):
    """A complete v2 summary without a cross-currency grand total."""

    schema_version: Literal["2"]
    complete: Literal[True]
    invoice_count: int
    unpaid_count: int
    overdue_count: int
    currencies: list[CurrencySummaryPayload]


class CurrencyComparisonPayload(TypedDict):
    """Aligned native-currency totals for both periods."""

    currency: str
    period_a_total: float
    period_b_total: float
    difference: float


class PeriodComparisonPayload(TypedDict):
    """A complete v2 comparison with an alphabetically ordered currency union."""

    schema_version: Literal["2"]
    complete: Literal[True]
    currencies: list[CurrencyComparisonPayload]


class ToolErrorPayload(TypedDict):
    """Sanitized read failure with an explicit recovery step and no amounts."""

    ok: Literal[False]
    what: str
    why: str
    retryable: bool
    next_step: str


class InvoiceListToolPayload(InvoiceListPayload):
    """A successful invoice-list tool response."""

    ok: Literal[True]


class InvoiceSummaryToolPayload(InvoiceSummaryPayload):
    """A successful currency-summary tool response."""

    ok: Literal[True]


class PeriodComparisonToolPayload(PeriodComparisonPayload):
    """A successful currency-comparison tool response."""

    ok: Literal[True]
