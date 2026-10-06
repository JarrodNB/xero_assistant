"""Purpose: Implement invoice operations against the Xero demo company.

Public API:
- XeroInvoiceService
"""

import re
from datetime import date
from typing import Any

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, LineItemPayload, UpdateInvoicePayload, VoidInvoicePayload
from app.invoices.gateway import ContactNotFoundError, InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import ContactRecord, InvoiceRecord
from app.invoices.summary import InvoiceSummary, PeriodComparison, compare_invoice_periods, summarize_invoice_records
from app.xero.client import XeroApiError, XeroClient
from app.xero.mapping import map_contact, map_invoice

INVOICE_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
INVOICE_STATUSES = frozenset({"DRAFT", "SUBMITTED", "AUTHORISED", "PAID", "VOIDED", "DELETED"})
PREFERRED_TAX_TYPES = ("NONE", "EXEMPTOUTPUT", "BASEXCLUDED", "ZERORATEDOUTPUT", "OUTPUT")
PAGE_LIMIT = 20


class XeroInvoiceService:
    """InvoiceGateway backed by the Xero Accounting API."""

    def __init__(self, client: XeroClient) -> None:
        """Store the Xero client and an empty account cache."""
        self._client = client
        self._account_code = ""
        self._tax_type = ""

    async def find_contacts(self, name: str) -> list[ContactRecord]:
        """Return contacts whose names contain the query."""
        raw_contacts = await self._search_contacts(name)
        return [map_contact(contact) for contact in raw_contacts]

    async def list_contacts(self, name: str | None = None) -> list[ContactRecord]:
        """Return contacts, optionally limited to names that contain the query."""
        if name:
            return await self.find_contacts(name)
        raw_contacts = await self._fetch_contacts()
        return [map_contact(contact) for contact in raw_contacts]

    async def find_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[InvoiceRecord]:
        """Return invoices matching the filters."""
        raw_invoices = await self._fetch_invoices(status, date_from, date_to)
        records = [map_invoice(invoice) for invoice in raw_invoices]
        if contact_name:
            needle = contact_name.casefold()
            records = [invoice for invoice in records if needle in invoice.contact_name.casefold()]
        return records

    async def get_invoice(self, invoice_number: str) -> InvoiceRecord:
        """Return one invoice, including its lines."""
        raw = await self._raw_invoice(invoice_number)
        return map_invoice(raw)

    async def summarize_invoices(
        self,
        contact_name: str | None,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
        today: date,
    ) -> InvoiceSummary:
        """Summarize invoices, including unpaid and overdue amounts."""
        invoices = await self.find_invoices(contact_name, status, date_from, date_to)
        return summarize_invoice_records(invoices, today)

    async def compare_invoice_totals(
        self,
        period_a_start: date,
        period_a_end: date,
        period_b_start: date,
        period_b_end: date,
    ) -> PeriodComparison:
        """Compare recognised totals for two date ranges."""
        start = min(period_a_start, period_b_start)
        end = max(period_a_end, period_b_end)
        invoices = await self.find_invoices(None, None, start, end)
        return compare_invoice_periods(invoices, period_a_start, period_a_end, period_b_start, period_b_end)

    async def create_contact(self, payload: CreateContactPayload) -> ContactRecord:
        """Create a contact in the demo company."""
        body: dict[str, Any] = {"Name": payload.name}
        if payload.email:
            body["EmailAddress"] = payload.email
        try:
            response = await self._client.post("/Contacts", {"Contacts": [body]})
        except XeroApiError as error:
            raise _from_xero(error) from error
        contacts = response.get("Contacts") or []
        if not contacts:
            raise InvoiceServiceError(
                "Contact was not created",
                "Xero returned no contact.",
                True,
                "Propose create_contact again.",
            )
        return map_contact(contacts[0])

    async def create_invoice(self, payload: CreateInvoicePayload) -> InvoiceRecord:
        """Create an authorised sales invoice for an existing contact."""
        contact = await self._exact_contact(payload.contact_name)
        account_code, tax_type = await self._sales_defaults()
        today = date.today()
        invoice = {
            "Type": "ACCREC",
            "Contact": {"ContactID": contact["ContactID"]},
            "LineItems": [_line_item(item, account_code, tax_type) for item in payload.line_items],
            "Date": today.isoformat(),
            "DueDate": payload.due_on(today).isoformat(),
            "Status": "AUTHORISED",
            "LineAmountTypes": "Exclusive",
            "Reference": payload.reference or "",
        }
        try:
            response = await self._client.post("/Invoices", {"Invoices": [invoice]})
        except XeroApiError as error:
            raise _from_xero(error) from error
        created = (response.get("Invoices") or [None])[0]
        if not created:
            raise InvoiceServiceError(
                "Invoice was not created",
                "Xero returned no invoice.",
                True,
                "Propose create_invoice again after checking the contact still exists.",
            )
        return map_invoice(created)

    async def update_invoice(self, payload: UpdateInvoicePayload) -> InvoiceRecord:
        """Update an existing invoice."""
        raw = await self._raw_invoice(payload.invoice_number)
        updated = {
            "InvoiceID": raw["InvoiceID"],
            "Type": raw.get("Type") or "ACCREC",
        }
        if payload.contact_name:
            contact = await self._exact_contact(payload.contact_name)
            updated["Contact"] = {"ContactID": contact["ContactID"]}
        if payload.reference is not None:
            updated["Reference"] = payload.reference
        if payload.due_date is not None:
            updated["DueDate"] = payload.due_date.isoformat()
        if payload.line_items is not None:
            account_code, tax_type = await self._sales_defaults()
            updated["LineItems"] = [_line_item(item, account_code, tax_type) for item in payload.line_items]
        try:
            response = await self._client.post("/Invoices", {"Invoices": [updated]})
        except XeroApiError as error:
            raise _from_xero(error) from error
        saved = (response.get("Invoices") or [None])[0]
        if not saved:
            raise InvoiceServiceError(
                "Invoice was not updated",
                "Xero returned no invoice.",
                True,
                "Load the invoice again and propose the update once more.",
            )
        return map_invoice(saved)

    async def void_invoice(self, payload: VoidInvoicePayload) -> InvoiceRecord:
        """Void an authorised invoice, or delete a draft."""
        raw = await self._raw_invoice(payload.invoice_number)
        status = str(raw.get("Status") or "")
        if status == "PAID":
            raise InvoiceServiceError(
                "Invoice cannot be voided",
                f"{payload.invoice_number} is paid.",
                False,
                "Leave the paid invoice as it is.",
            )
        next_status = "DELETED" if status == "DRAFT" else "VOIDED"
        try:
            response = await self._client.post(
                "/Invoices",
                {"Invoices": [{"InvoiceID": raw["InvoiceID"], "Status": next_status}]},
            )
        except XeroApiError as error:
            raise _from_xero(error) from error
        saved = (response.get("Invoices") or [None])[0]
        if not saved:
            raise InvoiceServiceError(
                "Invoice was not voided",
                "Xero returned no invoice.",
                True,
                "Load the invoice and try voiding it again.",
            )
        return map_invoice(saved)

    async def _fetch_contacts(self) -> list[dict[str, Any]]:
        """Page through contacts until a short page or the page cap."""
        rows: list[dict[str, Any]] = []
        for page in range(1, PAGE_LIMIT + 1):
            try:
                response = await self._client.get("/Contacts", {"page": page})
            except XeroApiError as error:
                raise _from_xero(error) from error
            batch = response.get("Contacts") or []
            rows.extend(batch)
            if len(batch) < 100:
                break
        return rows

    async def _search_contacts(self, name: str) -> list[dict[str, Any]]:
        """Search contacts and keep names that contain the query."""
        try:
            response = await self._client.get("/Contacts", {"searchTerm": name})
        except XeroApiError as error:
            raise _from_xero(error) from error
        needle = name.casefold()
        return [
            contact
            for contact in response.get("Contacts") or []
            if needle in str(contact.get("Name") or "").casefold()
        ]

    async def _exact_contact(self, name: str) -> dict[str, Any]:
        """Resolve one contact by exact name, without creating one."""
        matches = await self._search_contacts(name)
        exact = [contact for contact in matches if str(contact.get("Name") or "").casefold() == name.casefold()]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise InvoiceServiceError(
                "Contact name matches more than one contact",
                f"More than one contact is named {name}.",
                False,
                "Use the invoice UI to pick the right contact, then try again.",
            )
        if matches:
            names = ", ".join(str(contact.get("Name")) for contact in matches[:5])
            raise InvoiceServiceError(
                "Contact name is not an exact match",
                f"Similar contacts: {names}.",
                False,
                "Propose the action again with the exact contact name.",
            )
        raise ContactNotFoundError(name)

    async def _fetch_invoices(
        self,
        status: str | None,
        date_from: date | None,
        date_to: date | None,
    ) -> list[dict[str, Any]]:
        """Page through invoices for a status and date window."""
        where = _where_clause(status, date_from, date_to)
        rows: list[dict[str, Any]] = []
        for page in range(1, PAGE_LIMIT + 1):
            params: dict[str, Any] = {"page": page}
            if where:
                params["where"] = where
            try:
                response = await self._client.get("/Invoices", params)
            except XeroApiError as error:
                raise _from_xero(error) from error
            batch = response.get("Invoices") or []
            rows.extend(batch)
            if len(batch) < 100:
                break
        return rows

    async def _raw_invoice(self, invoice_number: str) -> dict[str, Any]:
        """Load one raw invoice so later writes can use its Xero id internally."""
        if not INVOICE_NUMBER.match(invoice_number):
            raise InvoiceServiceError(
                "Invoice number is invalid",
                "Invoice numbers may contain letters, numbers, and hyphens.",
                False,
                "Pass the invoice number shown in the invoice list.",
            )
        try:
            response = await self._client.get("/Invoices", {"where": f'InvoiceNumber=="{invoice_number}"'})
        except XeroApiError as error:
            raise _from_xero(error) from error
        invoices = response.get("Invoices") or []
        if not invoices:
            raise InvoiceNotFoundError(invoice_number)
        return invoices[0]

    async def _sales_defaults(self) -> tuple[str, str]:
        """Look up one revenue account and a sales tax type, preferring no tax."""
        if self._account_code and self._tax_type:
            return self._account_code, self._tax_type
        try:
            accounts = await self._client.get("/Accounts", {"where": 'Type=="REVENUE"&&Status=="ACTIVE"'})
            taxes = await self._client.get("/TaxRates")
        except XeroApiError as error:
            raise _from_xero(error) from error
        account_rows = accounts.get("Accounts") or []
        if not account_rows or not account_rows[0].get("Code"):
            raise InvoiceServiceError(
                "No sales account is available",
                "The demo company has no active revenue account.",
                False,
                "Add a revenue account in the Xero demo company, then try again.",
            )
        tax_rows = [
            tax
            for tax in taxes.get("TaxRates") or []
            if tax.get("Status") == "ACTIVE" and tax.get("CanApplyToRevenue")
        ]
        tax_type = ""
        for preferred in PREFERRED_TAX_TYPES:
            if any(tax.get("TaxType") == preferred for tax in tax_rows):
                tax_type = preferred
                break
        if not tax_type and tax_rows:
            tax_type = str(tax_rows[0].get("TaxType") or "")
        if not tax_type:
            raise InvoiceServiceError(
                "No sales tax rate is available",
                "The demo company has no tax rate that can apply to revenue.",
                False,
                "Check tax rates in the Xero demo company, then try again.",
            )
        self._account_code = str(account_rows[0]["Code"])
        self._tax_type = tax_type
        return self._account_code, self._tax_type


def _line_item(item: LineItemPayload, account_code: str, tax_type: str) -> dict[str, Any]:
    """Build one Xero line item."""
    return {
        "Description": item.description,
        "Quantity": item.quantity,
        "UnitAmount": item.unit_amount,
        "AccountCode": account_code,
        "TaxType": tax_type,
    }


def _where_clause(status: str | None, date_from: date | None, date_to: date | None) -> str:
    """Build a Xero where filter from validated fields."""
    parts: list[str] = []
    if status:
        if status not in INVOICE_STATUSES:
            raise InvoiceServiceError(
                "Invoice status is invalid",
                f"{status} is not a Xero invoice status.",
                False,
                "Use DRAFT, SUBMITTED, AUTHORISED, PAID, VOIDED, or leave status empty.",
            )
        parts.append(f'Status=="{status}"')
    if date_from:
        parts.append(f"Date>=DateTime({date_from.year},{date_from.month},{date_from.day})")
    if date_to:
        parts.append(f"Date<=DateTime({date_to.year},{date_to.month},{date_to.day})")
    return "&&".join(parts)


def _from_xero(error: XeroApiError) -> InvoiceServiceError:
    """Hide Xero internals while keeping a useful next step."""
    if error.message == "Xero is not connected.":
        return InvoiceServiceError(
            "Xero is not connected",
            "This server has no Demo Company authorisation.",
            False,
            "Choose Connect Xero and authorise the Demo Company.",
        )
    retryable = error.status_code >= 500 or error.status_code == 429
    return InvoiceServiceError(
        "Xero request failed",
        "The demo company did not accept the request.",
        retryable,
        "Retry once if this was a temporary Xero error. Otherwise adjust the invoice fields and try again.",
    )
