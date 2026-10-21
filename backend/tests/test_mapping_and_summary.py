"""Purpose: Tests for invoice summary math and Xero payload mapping.

Public API:
- test_unpaid_and_overdue_totals
- test_period_comparison_ignores_drafts_and_voids
- test_newest_invoices_come_first
- test_map_invoice_reads_date_strings
- test_map_invoice_reads_legacy_dates
- test_money_serialization_handles_large_decimals
- test_invoice_payload_preserves_four_decimal_quantity
"""

from datetime import date
from decimal import Decimal

from app.invoices.records import InvoiceRecord, LineItemRecord, invoice_payload, money, newest_first
from app.invoices.summary import compare_invoice_periods, summarize_invoice_records
from app.xero.mapping import map_invoice


def _invoice(
    number: str,
    status: str,
    total: str,
    amount_due: str,
    issued: date | None,
    due: date | None,
) -> InvoiceRecord:
    """Build an invoice record for summary tests."""
    return InvoiceRecord(
        invoice_number=number,
        contact_name="Bob's Construction",
        status=status,
        issued_on=issued,
        due_date=due,
        total=Decimal(total),
        amount_due=Decimal(amount_due),
        currency="AUD",
        reference=None,
    )


def test_unpaid_and_overdue_totals() -> None:
    """Unpaid includes authorised balances, and overdue is the past-due subset."""
    today = date(2026, 10, 6)
    summary = summarize_invoice_records(
        [
            _invoice("INV-1", "AUTHORISED", "55", "55", date(2026, 9, 1), date(2026, 9, 15)),
            _invoice("INV-2", "AUTHORISED", "20", "20", date(2026, 10, 1), date(2026, 10, 20)),
            _invoice("INV-3", "PAID", "40", "0", date(2026, 8, 1), date(2026, 8, 15)),
            _invoice("INV-4", "DRAFT", "10", "10", date(2026, 9, 1), date(2026, 9, 2)),
        ],
        today,
    )
    assert summary.unpaid_count == 2
    assert summary.currencies[0].unpaid_total == Decimal("75")
    assert summary.overdue_count == 1
    assert summary.currencies[0].overdue_total == Decimal("55")


def test_period_comparison_ignores_drafts_and_voids() -> None:
    """Recognised revenue is authorised and paid invoices inside each range."""
    invoices = [
        _invoice("INV-1", "AUTHORISED", "100", "100", date(2026, 1, 15), date(2026, 2, 1)),
        _invoice("INV-2", "PAID", "40", "0", date(2026, 2, 10), date(2026, 2, 20)),
        _invoice("INV-3", "DRAFT", "999", "999", date(2026, 2, 11), date(2026, 2, 20)),
        _invoice("INV-4", "VOIDED", "50", "0", date(2026, 2, 12), date(2026, 2, 20)),
    ]
    comparison = compare_invoice_periods(
        invoices,
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 2, 1),
        date(2026, 2, 28),
    )
    assert comparison.currencies[0].period_a_total == Decimal("100")
    assert comparison.currencies[0].period_b_total == Decimal("40")
    assert comparison.currencies[0].difference == Decimal("-60")


def test_newest_invoices_come_first() -> None:
    """Issue date descending puts the latest invoice first and undated ones last."""
    ordered = newest_first(
        [
            _invoice("OLD", "AUTHORISED", "10", "10", date(2026, 1, 2), None),
            _invoice("NONE", "DRAFT", "5", "5", None, None),
            _invoice("NEW", "PAID", "20", "0", date(2026, 8, 9), None),
            _invoice("MID", "AUTHORISED", "15", "15", date(2026, 3, 4), None),
        ]
    )
    assert [invoice.invoice_number for invoice in ordered] == ["NEW", "MID", "OLD", "NONE"]


def test_map_invoice_reads_date_strings() -> None:
    """DateString fields become dates and Xero ids stay off the record."""
    invoice = map_invoice(
        {
            "InvoiceID": "hidden-id",
            "InvoiceNumber": "INV-001",
            "Status": "AUTHORISED",
            "Contact": {"ContactID": "hidden-contact", "Name": "Bob's Construction"},
            "DateString": "2026-09-01T00:00:00",
            "DueDateString": "2026-09-15T00:00:00",
            "Total": 55,
            "AmountDue": 55,
            "CurrencyCode": "AUD",
            "Reference": "Roof",
            "LineItems": [{"Description": "Labour", "Quantity": 1, "UnitAmount": 55}],
        }
    )
    assert invoice.invoice_number == "INV-001"
    assert invoice.contact_name == "Bob's Construction"
    assert invoice.issued_on == date(2026, 9, 1)
    assert invoice.due_date == date(2026, 9, 15)
    assert invoice.total == Decimal("55")
    assert invoice.line_items[0].description == "Labour"
    assert not hasattr(invoice, "invoice_id")


def test_map_invoice_reads_legacy_dates() -> None:
    """The /Date(milliseconds)/ form maps to a UTC date."""
    invoice = map_invoice({"Date": "/Date(1756684800000+0000)/", "DueDate": "/Date(1757894400000+0000)/"})
    assert invoice.issued_on == date(2025, 9, 1)
    assert invoice.due_date == date(2025, 9, 15)


def test_money_serialization_handles_large_decimals() -> None:
    """A large but supported amount can be rounded without Decimal context overflow."""
    assert money(Decimal("999999999999.999")) == 1_000_000_000_000.0


def test_invoice_payload_preserves_four_decimal_quantity() -> None:
    """Invoice responses retain quantities that use the supported four decimal places."""
    invoice = _invoice("INV-1", "AUTHORISED", "0.01", "0.01", date(2026, 10, 10), None)
    invoice = InvoiceRecord(
        invoice_number=invoice.invoice_number,
        contact_name=invoice.contact_name,
        status=invoice.status,
        issued_on=invoice.issued_on,
        due_date=invoice.due_date,
        total=invoice.total,
        amount_due=invoice.amount_due,
        currency=invoice.currency,
        reference=invoice.reference,
        line_items=(LineItemRecord("Usage", Decimal("0.0001"), Decimal("55.00")),),
    )
    assert invoice_payload(invoice, include_lines=True)["line_items"] == [
        {"description": "Usage", "quantity": 0.0001, "unit_amount": 55.0}
    ]
