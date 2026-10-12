"""Purpose: Invoice and contact values shared by Xero, tools, and the UI.

Public API:
- LineItemRecord
- InvoiceRecord
- ContactRecord
- money
- newest_first
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext


def money(value: Decimal) -> float:
    """Round a decimal amount to two places and return a float."""
    return _decimal_number(value, 2)


def _decimal_number(value: Decimal, decimal_places: int) -> float:
    """Round a decimal to the requested places without context overflow."""
    integer_digits = max(value.adjusted() + 1, 1) if value.is_finite() else 1
    with localcontext() as context:
        context.prec = max(integer_digits + decimal_places, 28)
        quantum = Decimal(1).scaleb(-decimal_places)
        return float(value.quantize(quantum))


@dataclass(frozen=True)
class LineItemRecord:
    """One invoice line the UI and the model can see."""

    description: str
    quantity: Decimal
    unit_amount: Decimal
    line_item_id: str | None = None
    has_explicit_tax: bool = False


@dataclass(frozen=True)
class ContactRecord:
    """A contact identified by name, without a Xero id."""

    name: str
    email: str | None = None


@dataclass(frozen=True)
class InvoiceRecord:
    """An invoice identified by its invoice number, without a Xero id."""

    invoice_number: str
    contact_name: str
    status: str
    issued_on: date | None
    due_date: date | None
    total: Decimal
    amount_due: Decimal
    currency: str
    reference: str | None
    line_items: tuple[LineItemRecord, ...] = ()
    line_editing_supported: bool = True


def newest_first(invoices: list[InvoiceRecord]) -> list[InvoiceRecord]:
    """Order invoices by issue date, newest first. Undated invoices stay last."""
    return sorted(invoices, key=lambda invoice: invoice.issued_on or date.min, reverse=True)


def contact_payload(contact: ContactRecord) -> dict[str, object]:
    """Serialize a contact for JSON responses."""
    return {"name": contact.name, "email": contact.email}


def invoice_payload(invoice: InvoiceRecord, include_lines: bool = False, *, include_edit_details: bool = False) -> dict[str, object]:
    """Serialize an invoice for JSON responses."""
    body: dict[str, object] = {
        "invoice_number": invoice.invoice_number,
        "contact_name": invoice.contact_name,
        "status": invoice.status,
        "date": invoice.issued_on.isoformat() if invoice.issued_on else None,
        "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
        "total": money(invoice.total),
        "amount_due": money(invoice.amount_due),
        "currency": invoice.currency,
        "reference": invoice.reference,
    }
    if include_lines:
        serialized_lines = [
            {
                "description": item.description,
                "quantity": _decimal_number(item.quantity, 4),
                "unit_amount": money(item.unit_amount),
            }
            for item in invoice.line_items
        ]
        if include_edit_details:
            body["line_editing_supported"] = invoice.line_editing_supported
            for serialized, item in zip(serialized_lines, invoice.line_items):
                serialized.update(line_item_id=item.line_item_id, has_explicit_tax=item.has_explicit_tax)
                serialized["unit_amount"] = _decimal_number(item.unit_amount, 4)
        body["line_items"] = serialized_lines
    return body
