"""Purpose: In-memory invoice gateway for API tests.

Public API:
- FakeInvoiceGateway
"""

from datetime import date
from decimal import Decimal

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, UpdateInvoicePayload, VoidInvoicePayload
from app.invoices.gateway import ContactNotFoundError, InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import ContactRecord, InvoiceRecord, LineItemRecord, newest_first
from app.invoices.summary import PeriodComparison, compare_invoice_periods, summarize_invoice_records


class FakeInvoiceGateway:
    """Invoice gateway that records writes and never calls Xero."""

    def __init__(self) -> None:
        """Start with no contacts or invoices."""
        self.contacts: list[ContactRecord] = []
        self.invoices: list[InvoiceRecord] = []
        self.write_calls: list[str] = []
        self.read_calls: list[str] = []
        self._next_number = 1001

    async def find_contacts(self, name: str) -> list[ContactRecord]:
        """Return contacts whose names contain the query."""
        self.read_calls.append("find_contacts")
        needle = name.casefold()
        return [contact for contact in self.contacts if needle in contact.name.casefold()]

    async def list_contacts(self, name: str | None = None) -> list[ContactRecord]:
        """Return contacts, optionally limited to names that contain the query."""
        self.read_calls.append("list_contacts")
        if not name:
            return list(self.contacts)
        needle = name.casefold()
        return [contact for contact in self.contacts if needle in contact.name.casefold()]

    async def find_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[InvoiceRecord]:
        """Return invoices matching the filters, newest issue date first."""
        self.read_calls.append("find_invoices")
        rows = self.invoices
        if contact_name:
            needle = contact_name.casefold()
            rows = [invoice for invoice in rows if needle in invoice.contact_name.casefold()]
        if status:
            rows = [invoice for invoice in rows if invoice.status == status]
        if date_from:
            rows = [invoice for invoice in rows if invoice.issued_on and invoice.issued_on >= date_from]
        if date_to:
            rows = [invoice for invoice in rows if invoice.issued_on and invoice.issued_on <= date_to]
        return newest_first(rows)

    async def get_invoice(self, invoice_number: str) -> InvoiceRecord:
        """Return one invoice."""
        self.read_calls.append("get_invoice")
        for invoice in self.invoices:
            if invoice.invoice_number == invoice_number:
                return invoice
        raise InvoiceNotFoundError(invoice_number)

    async def summarize_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
        today: date,
    ):
        """Summarize the in-memory invoices."""
        self.read_calls.append("summarize_invoices")
        invoices = await self.find_invoices(contact_name, status, date_from, date_to)
        self.read_calls.pop()
        return summarize_invoice_records(invoices, today)

    async def compare_invoice_totals(
        self,
        period_a_start: date,
        period_a_end: date,
        period_b_start: date,
        period_b_end: date,
    ) -> PeriodComparison:
        """Compare recognised totals in memory."""
        self.read_calls.append("compare_invoice_totals")
        return compare_invoice_periods(
            self.invoices,
            period_a_start,
            period_a_end,
            period_b_start,
            period_b_end,
        )

    async def create_contact(self, payload: CreateContactPayload) -> ContactRecord:
        """Store a contact."""
        self.write_calls.append("create_contact")
        contact = ContactRecord(name=payload.name, email=payload.email)
        self.contacts.append(contact)
        return contact

    async def create_invoice(self, payload: CreateInvoicePayload) -> InvoiceRecord:
        """Store an invoice only when the contact already exists."""
        if not any(contact.name.casefold() == payload.contact_name.casefold() for contact in self.contacts):
            raise ContactNotFoundError(payload.contact_name)
        self.write_calls.append("create_invoice")
        total = sum((Decimal(str(item.quantity)) * Decimal(str(item.unit_amount)) for item in payload.line_items), Decimal("0"))
        invoice = InvoiceRecord(
            invoice_number=f"INV-{self._next_number}",
            contact_name=payload.contact_name,
            status="AUTHORISED",
            issued_on=date.today(),
            due_date=payload.due_on(date.today()),
            total=total,
            amount_due=total,
            currency="AUD",
            reference=payload.reference,
            line_items=tuple(
                LineItemRecord(
                    description=item.description,
                    quantity=Decimal(str(item.quantity)),
                    unit_amount=Decimal(str(item.unit_amount)),
                )
                for item in payload.line_items
            ),
        )
        self._next_number += 1
        self.invoices.append(invoice)
        return invoice

    async def update_invoice(self, payload: UpdateInvoicePayload) -> InvoiceRecord:
        """Replace matching invoice fields."""
        if payload.contact_name and not any(
            contact.name.casefold() == payload.contact_name.casefold() for contact in self.contacts
        ):
            raise ContactNotFoundError(payload.contact_name)
        current = await self.get_invoice(payload.invoice_number)
        self.read_calls.pop()
        self.write_calls.append("update_invoice")
        updated = InvoiceRecord(
            invoice_number=current.invoice_number,
            contact_name=payload.contact_name or current.contact_name,
            status=current.status,
            issued_on=current.issued_on,
            due_date=payload.due_date or current.due_date,
            total=current.total,
            amount_due=current.amount_due,
            currency=current.currency,
            reference=payload.reference if payload.reference is not None else current.reference,
            line_items=current.line_items,
        )
        self.invoices = [updated if invoice.invoice_number == current.invoice_number else invoice for invoice in self.invoices]
        return updated

    async def void_invoice(self, payload: VoidInvoicePayload) -> InvoiceRecord:
        """Mark an invoice voided."""
        current = await self.get_invoice(payload.invoice_number)
        self.read_calls.pop()
        if current.status == "PAID":
            raise InvoiceServiceError(
                "Invoice cannot be voided",
                f"{payload.invoice_number} is paid.",
                False,
                "Leave the paid invoice as it is.",
            )
        self.write_calls.append("void_invoice")
        updated = InvoiceRecord(
            invoice_number=current.invoice_number,
            contact_name=current.contact_name,
            status="VOIDED",
            issued_on=current.issued_on,
            due_date=current.due_date,
            total=current.total,
            amount_due=Decimal("0"),
            currency=current.currency,
            reference=current.reference,
            line_items=current.line_items,
        )
        self.invoices = [updated if invoice.invoice_number == current.invoice_number else invoice for invoice in self.invoices]
        return updated
