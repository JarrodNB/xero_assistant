"""Purpose: HTTP routes for the invoice list and editor.

Public API:
- router
"""

from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Request

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, UpdateInvoicePayload, VoidInvoicePayload, summarize_action
from app.actions.service import load_action, run_confirmed_action
from app.auth.routes import require_user
from app.errors import ApiError
from app.invoices.gateway import InvoiceNotFoundError, InvoiceServiceError
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
    raise ApiError(502 if error.outcome_unknown else 409, error.what, error.why, error.retryable, error.next_step, outcome_unknown=error.outcome_unknown)


@router.get("/contacts")
async def list_contacts(request: Request, name: str | None = None) -> dict[str, object]:
    """List contacts, optionally filtered by name."""
    services = _services(request)
    try:
        contacts = await services.invoices.list_contacts(name or None)
    except InvoiceServiceError as error:
        _raise_service_error(error)
    return {"contacts": [contact_payload(contact) for contact in contacts]}


@router.post("/contacts")
async def create_contact(body: CreateContactPayload, request: Request) -> dict[str, object]:
    """Create a contact. The save button is the confirmation."""
    return await _editor_write(request, "create_contact", body.model_dump(mode="json"), "contact")


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
    return await _editor_write(request, "create_invoice", body.model_dump(mode="json"), "invoice")


@router.put("/invoices/{invoice_number}")
async def update_invoice(invoice_number: str, body: UpdateInvoicePayload, request: Request) -> dict[str, object]:
    """Update an invoice. The save button is the confirmation."""
    payload = body.model_copy(update={"invoice_number": invoice_number})
    return await _editor_write(request, "update_invoice", payload.model_dump(mode="json"), "invoice")


@router.post("/invoices/{invoice_number}/void")
async def void_invoice(invoice_number: str, request: Request) -> dict[str, object]:
    """Void an invoice. The void button is the confirmation."""
    payload = VoidInvoicePayload(invoice_number=invoice_number)
    return await _editor_write(request, "void_invoice", payload.model_dump(mode="json"), "invoice")


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

async def _editor_write(request: Request, action_type: str, payload: dict, result_field: str) -> dict[str, object]:
    """Deduplicate editor retries by request id and freeze the first validated payload."""
    services = _services(request)
    supplied_id = request.headers.get("X-Write-Id")
    try:
        request_id = str(UUID(supplied_id)) if supplied_id else str(uuid4())
    except ValueError as error:
        raise ApiError(422, "Write id is invalid", "X-Write-Id must be a UUID.", False, "Use one UUID per intentional write and reuse it for retries.") from error
    summary = summarize_action(action_type, payload)
    action = services.actions.create_ui_action(request_id, action_type, payload, summary)
    if action.action_type != action_type or action.payload != payload:
        raise ApiError(409, "Write id was reused", "This write id belongs to a different request.", False, "Review the earlier write before starting a new intentional action.")
    action = load_action(services.actions, action.id, request.app.state.settings.action_execution_timeout_seconds)
    result = await run_confirmed_action(services, action, payload, summary, request.app.state.settings.action_execution_timeout_seconds)
    if result.get("status") != "executed":
        unknown = result.get("status") == "unknown"
        raise ApiError(502 if unknown else 409, "Execution outcome is unknown" if unknown else "Write is still executing", "This write will not be submitted again.", False, str(result.get("next_step", "Check the recorded result.")), outcome_unknown=unknown)
    return {result_field: result[result_field]}
