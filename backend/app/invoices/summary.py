"""Purpose: Pure invoice totals for unpaid, overdue, and period comparisons.

Public API:
- InvoiceSummary
- PeriodComparison
- summarize_invoice_records
- compare_invoice_periods
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.invoices.records import InvoiceRecord, money

RECOGNIZED_STATUSES = frozenset({"AUTHORISED", "PAID"})


@dataclass(frozen=True)
class InvoiceSummary:
    """Counts and amounts for a set of invoices."""

    invoice_count: int
    unpaid_count: int
    unpaid_total: Decimal
    overdue_count: int
    overdue_total: Decimal
    invoice_total: Decimal


@dataclass(frozen=True)
class PeriodComparison:
    """Recognised invoice totals for two date ranges."""

    period_a_total: Decimal
    period_b_total: Decimal
    difference: Decimal


def summarize_invoice_records(invoices: list[InvoiceRecord], today: date) -> InvoiceSummary:
    """Sum unpaid and overdue amounts inside an invoice list."""
    unpaid = [invoice for invoice in invoices if invoice.status == "AUTHORISED" and invoice.amount_due > 0]
    overdue = [
        invoice
        for invoice in unpaid
        if invoice.due_date is not None and invoice.due_date < today
    ]
    return InvoiceSummary(
        invoice_count=len(invoices),
        unpaid_count=len(unpaid),
        unpaid_total=sum((invoice.amount_due for invoice in unpaid), Decimal("0")),
        overdue_count=len(overdue),
        overdue_total=sum((invoice.amount_due for invoice in overdue), Decimal("0")),
        invoice_total=sum((invoice.total for invoice in invoices), Decimal("0")),
    )


def compare_invoice_periods(
    invoices: list[InvoiceRecord],
    period_a_start: date,
    period_a_end: date,
    period_b_start: date,
    period_b_end: date,
) -> PeriodComparison:
    """Compare recognised invoice totals across two inclusive date ranges."""
    period_a_total = _recognised_total(invoices, period_a_start, period_a_end)
    period_b_total = _recognised_total(invoices, period_b_start, period_b_end)
    return PeriodComparison(
        period_a_total=period_a_total,
        period_b_total=period_b_total,
        difference=period_b_total - period_a_total,
    )


def summary_payload(summary: InvoiceSummary) -> dict[str, object]:
    """Serialize a summary for JSON responses."""
    return {
        "invoice_count": summary.invoice_count,
        "unpaid_count": summary.unpaid_count,
        "unpaid_total": money(summary.unpaid_total),
        "overdue_count": summary.overdue_count,
        "overdue_total": money(summary.overdue_total),
        "invoice_total": money(summary.invoice_total),
    }


def comparison_payload(comparison: PeriodComparison) -> dict[str, float]:
    """Serialize a period comparison for JSON responses."""
    return {
        "period_a_total": money(comparison.period_a_total),
        "period_b_total": money(comparison.period_b_total),
        "difference": money(comparison.difference),
    }


def _recognised_total(invoices: list[InvoiceRecord], start: date, end: date) -> Decimal:
    """Sum invoice totals whose issue date falls in the range and whose status counts as revenue."""
    return sum(
        (
            invoice.total
            for invoice in invoices
            if invoice.status in RECOGNIZED_STATUSES
            and invoice.issued_on is not None
            and start <= invoice.issued_on <= end
        ),
        Decimal("0"),
    )
