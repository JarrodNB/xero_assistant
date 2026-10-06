"""Purpose: HTTP routes for the invoice list and editor.

Public API:
- router
"""

from datetime import date

from fastapi import APIRouter, Query, Request

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, UpdateInvoicePayload, VoidInvoicePayload
from app.auth.routes import require_user
from app.errors import ApiError
from app.invoices.gateway import ContactNotFoundError, InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import contact_payload, invoice_payload
from app.invoices.summary import comparison_payload, summary_payload
from app.runtime import AppServices

router = APIRouter(tags=["invoices"])


def _services(request: Request) -> AppServices:
    """Return the invoice gateway bound to this app."""
    require_user(request)
    return request.app.state.services


def _raise_service_error(error: InvoiceServiceError) -> None:
    """Convert a service error into an API error."""
    raise ApiError(409, error.what, error.why, error.retryable, error.next_step)


@router.get("/contacts")
async def list_contacts(request: Request, name: str = Query(min_length=1)) -> dict[str, object]:
    """Find contacts by name."""
    services = _services(request)
    try:
        contacts = await services.invoices.find_contacts(name)
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"contacts": [contact_payload(contact) for contact in contacts]}


@router.post("/contacts")
async def create_contact(body: CreateContactPayload, request: Request) -> dict[str, object]:
    """Create a contact. The save button is the confirmation."""
    services = _services(request)
    try:
        contact = await services.invoices.create_contact(body)
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"contact": contact_payload(contact)}


@router.get("/invoices")
async def list_invoices(
    request: Request,
    contact_name: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    """List invoices for the invoice screen."""
    services = _services(request)
    try:
        invoices = await services.invoices.find_invoices(contact_name, status, date_from, date_to)
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"invoices": [invoice_payload(invoice) for invoice in invoices]}


@router.get("/invoices/{invoice_number}")
async def get_invoice(invoice_number: str, request: Request) -> dict[str, object]:
    """Load one invoice for the editor."""
    services = _services(request)
    try:
        invoice = await services.invoices.get_invoice(invoice_number)
    except InvoiceNotFoundError as error:
        raise ApiError(
            404,
            "Invoice does not exist",
            f"No invoice is numbered {error.invoice_number}.",
            False,
            "Return to the invoice list and choose another invoice.",
        ) from error
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"invoice": invoice_payload(invoice, include_lines=True)}


@router.post("/invoices")
async def create_invoice(body: CreateInvoicePayload, request: Request) -> dict[str, object]:
    """Create an invoice. The save button is the confirmation."""
    services = _services(request)
    try:
        invoice = await services.invoices.create_invoice(body)
    except ContactNotFoundError as error:
        raise ApiError(
            409,
            "Contact does not exist",
            f"No contact is named {error.name}.",
            False,
            "Create the contact first, then save the invoice.",
        ) from error
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"invoice": invoice_payload(invoice, include_lines=True)}


@router.put("/invoices/{invoice_number}")
async def update_invoice(invoice_number: str, body: UpdateInvoicePayload, request: Request) -> dict[str, object]:
    """Update an invoice. The save button is the confirmation."""
    services = _services(request)
    payload = body.model_copy(update={"invoice_number": invoice_number})
    try:
        invoice = await services.invoices.update_invoice(payload)
    except ContactNotFoundError as error:
        raise ApiError(
            409,
            "Contact does not exist",
            f"No contact is named {error.name}.",
            False,
            "Create the contact first, then save the invoice.",
        ) from error
    except InvoiceNotFoundError as error:
        raise ApiError(
            404,
            "Invoice does not exist",
            f"No invoice is numbered {error.invoice_number}.",
            False,
            "Return to the invoice list and choose another invoice.",
        ) from error
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"invoice": invoice_payload(invoice, include_lines=True)}


@router.post("/invoices/{invoice_number}/void")
async def void_invoice(invoice_number: str, request: Request) -> dict[str, object]:
    """Void an invoice. The void button is the confirmation."""
    services = _services(request)
    try:
        invoice = await services.invoices.void_invoice(VoidInvoicePayload(invoice_number=invoice_number))
    except InvoiceNotFoundError as error:
        raise ApiError(
            404,
            "Invoice does not exist",
            f"No invoice is numbered {error.invoice_number}.",
            False,
            "Return to the invoice list.",
        ) from error
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"invoice": invoice_payload(invoice, include_lines=True)}


@router.get("/invoice-summary")
async def invoice_summary(
    request: Request,
    contact_name: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    """Return unpaid, overdue, and total figures for the current filters."""
    services = _services(request)
    try:
        summary = await services.invoices.summarize_invoices(contact_name, status, date_from, date_to, date.today())
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return summary_payload(summary)


@router.get("/invoice-comparison")
async def invoice_comparison(
    request: Request,
    period_a_start: date,
    period_a_end: date,
    period_b_start: date,
    period_b_end: date,
) -> dict[str, float]:
    """Compare recognised invoice totals for two date ranges."""
    services = _services(request)
    try:
        comparison = await services.invoices.compare_invoice_totals(
            period_a_start,
            period_a_end,
            period_b_start,
            period_b_end,
        )
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return comparison_payload(comparison)
