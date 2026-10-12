"""Purpose: Invoice and contact operations the UI and confirmed actions share.

Public API:
- InvoiceGateway
- ContactNotFoundError
- InvoiceNotFoundError
- InvoiceServiceError
"""

from datetime import date
from typing import Protocol

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, UpdateInvoicePayload, VoidInvoicePayload
from app.invoices.records import ContactRecord, InvoiceRecord
from app.invoices.summary import InvoiceSummary, PeriodComparison


class ContactNotFoundError(Exception):
    """The named contact is not in the demo company."""

    def __init__(self, name: str) -> None:
        """Store the contact name that was missing."""
        self.name = name
        super().__init__(name)


class InvoiceNotFoundError(Exception):
    """The invoice number is not in the demo company."""

    def __init__(self, invoice_number: str) -> None:
        """Store the invoice number that was missing."""
        self.invoice_number = invoice_number
        super().__init__(invoice_number)


class InvoiceServiceError(Exception):
    """A business rule stopped an invoice operation."""

    def __init__(self, what: str, why: str, retryable: bool, next_step: str, *, outcome_unknown: bool = False) -> None:
        """Store an explanation safe to show to a person or the model."""
        self.what = what
        self.why = why
        self.retryable = retryable
        self.next_step = next_step
        self.outcome_unknown = outcome_unknown
        super().__init__(what)


class InvoiceGateway(Protocol):
    """Read and write invoices without exposing Xero ids."""

    async def find_contacts(self, name: str) -> list[ContactRecord]:
        """Return contacts whose names contain the query."""

    async def list_contacts(self, name: str | None = None) -> list[ContactRecord]:
        """Return contacts, optionally limited to names that contain the query."""

    async def find_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[InvoiceRecord]:
        """Return invoices matching the filters."""

    async def get_invoice(self, invoice_number: str) -> InvoiceRecord:
        """Return one invoice, including its lines."""

    async def summarize_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
        today: date,
    ) -> InvoiceSummary:
        """Summarize invoices, including unpaid and overdue amounts."""

    async def compare_invoice_totals(
        self,
        period_a_start: date,
        period_a_end: date,
        period_b_start: date,
        period_b_end: date,
    ) -> PeriodComparison:
        """Compare recognised totals for two date ranges."""

    async def create_contact(self, payload: CreateContactPayload) -> ContactRecord:
        """Create a contact."""

    async def create_invoice(self, payload: CreateInvoicePayload) -> InvoiceRecord:
        """Create an authorised sales invoice for an existing contact."""

    async def update_invoice(self, payload: UpdateInvoicePayload) -> InvoiceRecord:
        """Update an existing invoice."""

    async def void_invoice(self, payload: VoidInvoicePayload) -> InvoiceRecord:
        """Void an invoice, or delete it when it is still a draft."""
