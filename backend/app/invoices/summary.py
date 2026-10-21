"""Purpose: Complete, currency-separated invoice totals and comparisons.

Public API:
- InvoiceSummary, CurrencySummary, PeriodComparison, CurrencyComparison
- summarize_invoice_records, compare_invoice_periods
- summary_payload, comparison_payload, validate_date_range
"""

from dataclasses import dataclass, asdict
from datetime import date
from decimal import Decimal

from app.invoices.records import InvoiceRecord, money

RECOGNIZED_STATUSES = frozenset({"AUTHORISED", "PAID"})
SCHEMA_VERSION = "2"


@dataclass(frozen=True)
class CurrencySummary:
    """Counts and native-currency amounts for one currency."""

    currency: str
    invoice_count: int
    unpaid_count: int
    unpaid_total: Decimal
    overdue_count: int
    overdue_total: Decimal
    invoice_total: Decimal


@dataclass(frozen=True)
class InvoiceSummary:
    """Complete invoice counts and alphabetically ordered currency groups."""

    invoice_count: int
    unpaid_count: int
    overdue_count: int
    currencies: tuple[CurrencySummary, ...]


@dataclass(frozen=True)
class CurrencyComparison:
    """Aligned recognised totals; a missing period has zero in this currency."""

    currency: str
    period_a_total: Decimal
    period_b_total: Decimal
    difference: Decimal


@dataclass(frozen=True)
class PeriodComparison:
    """Complete recognised totals grouped by currency without conversion."""

    currencies: tuple[CurrencyComparison, ...]


def validate_date_range(start: date | None, end: date | None) -> None:
    """Reject reversed inclusive ranges before querying or computing totals."""
    if start is not None and end is not None and start > end:
        raise ValueError("The start date must be on or before the end date.")


def _currency(invoice: InvoiceRecord) -> str:
    """Refuse amounts without an authoritative currency rather than guessing."""
    currency = invoice.currency.strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValueError("An invoice has no valid currency; check its currency in Xero.")
    return currency


def summarize_invoice_records(invoices: list[InvoiceRecord], today: date) -> InvoiceSummary:
    """Compute unpaid and overdue balances separately for each native currency."""
    groups: dict[str, list[InvoiceRecord]] = {}
    for invoice in invoices:
        groups.setdefault(_currency(invoice), []).append(invoice)
    currencies = []
    for currency, rows in sorted(groups.items()):
        unpaid = [row for row in rows if row.status == "AUTHORISED" and row.amount_due > 0]
        overdue = [row for row in unpaid if row.due_date is not None and row.due_date < today]
        currencies.append(CurrencySummary(
            currency, len(rows), len(unpaid), sum((row.amount_due for row in unpaid), Decimal("0")),
            len(overdue), sum((row.amount_due for row in overdue), Decimal("0")),
            sum((row.total for row in rows), Decimal("0")),
        ))
    return InvoiceSummary(len(invoices), sum(row.unpaid_count for row in currencies),
                          sum(row.overdue_count for row in currencies), tuple(currencies))


def compare_invoice_periods(
    invoices: list[InvoiceRecord], period_a_start: date, period_a_end: date,
    period_b_start: date, period_b_end: date,
) -> PeriodComparison:
    """Compare recognised totals for each currency occurring in either period."""
    validate_date_range(period_a_start, period_a_end)
    validate_date_range(period_b_start, period_b_end)
    totals: dict[str, list[Decimal]] = {}
    for invoice in invoices:
        if invoice.status not in RECOGNIZED_STATUSES or invoice.issued_on is None:
            continue
        in_a = period_a_start <= invoice.issued_on <= period_a_end
        in_b = period_b_start <= invoice.issued_on <= period_b_end
        if not in_a and not in_b:
            continue
        values = totals.setdefault(_currency(invoice), [Decimal("0"), Decimal("0")])
        if in_a:
            values[0] += invoice.total
        if in_b:
            values[1] += invoice.total
    return PeriodComparison(tuple(CurrencyComparison(currency, a, b, b - a)
                                  for currency, (a, b) in sorted(totals.items())))


def _amount_payload(group: CurrencySummary | CurrencyComparison) -> dict[str, object]:
    """Serialize Decimal amounts while retaining currency and counts."""
    return {key: money(value) if isinstance(value, Decimal) else value
            for key, value in asdict(group).items()}


def summary_payload(summary: InvoiceSummary) -> dict[str, object]:
    """Serialize a complete v2 summary; empty results have no currency groups."""
    return {"schema_version": SCHEMA_VERSION, "complete": True,
            "invoice_count": summary.invoice_count, "unpaid_count": summary.unpaid_count,
            "overdue_count": summary.overdue_count,
            "currencies": [_amount_payload(group) for group in summary.currencies]}


def comparison_payload(comparison: PeriodComparison) -> dict[str, object]:
    """Serialize aligned v2 totals without a cross-currency grand total."""
    return {"schema_version": SCHEMA_VERSION, "complete": True,
            "currencies": [_amount_payload(group) for group in comparison.currencies]}
