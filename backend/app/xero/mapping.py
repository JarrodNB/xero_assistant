"""Purpose: Turn Xero invoice and contact payloads into local records.

Public API:
- map_contact
- map_invoice
- parse_xero_date
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from app.invoices.records import ContactRecord, InvoiceRecord, LineItemRecord


def map_contact(raw: dict) -> ContactRecord:
    """Map a Xero contact object onto a contact record."""
    return ContactRecord(name=str(raw.get("Name") or ""), email=raw.get("EmailAddress") or None)


def map_invoice(raw: dict) -> InvoiceRecord:
    """Map a Xero invoice object onto an invoice record."""
    contact = raw.get("Contact") or {}
    line_items = tuple(
        LineItemRecord(
            description=str(item.get("Description") or ""),
            quantity=_decimal(item.get("Quantity")),
            unit_amount=_decimal(item.get("UnitAmount")),
        )
        for item in raw.get("LineItems") or []
    )
    return InvoiceRecord(
        invoice_number=str(raw.get("InvoiceNumber") or ""),
        contact_name=str(contact.get("Name") or ""),
        status=str(raw.get("Status") or ""),
        issued_on=parse_xero_date(raw, "Date"),
        due_date=parse_xero_date(raw, "DueDate"),
        total=_decimal(raw.get("Total")),
        amount_due=_decimal(raw.get("AmountDue")),
        currency=str(raw.get("CurrencyCode") or ""),
        reference=raw.get("Reference") or None,
        line_items=line_items,
    )


def parse_xero_date(raw: dict, field: str) -> date | None:
    """Read a Xero date field from DateString or the legacy /Date()/ form."""
    string_value = raw.get(f"{field}String")
    if isinstance(string_value, str) and len(string_value) >= 10:
        return date.fromisoformat(string_value[:10])
    value = raw.get(field)
    if isinstance(value, str) and value.startswith("/Date("):
        end = value.find("+")
        if end == -1:
            end = value.find(")")
        millis = int(value[6:end])
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()
    if isinstance(value, str) and len(value) >= 10:
        return date.fromisoformat(value[:10])
    return None


def _decimal(value: object) -> Decimal:
    """Convert a Xero number into a decimal."""
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))
