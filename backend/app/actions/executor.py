"""Purpose: Execute one confirmed action through the invoice service.

Public API:
- execute_action
- failure_body
"""

from app.actions.payloads import CreateContactPayload, CreateInvoicePayload, UpdateInvoicePayload, VoidInvoicePayload, parse_action
from app.db.repository import StoredAction
from app.errors import ApiError
from app.invoices.gateway import ContactNotFoundError, InvoiceGateway, InvoiceNotFoundError, InvoiceServiceError
from app.invoices.records import contact_payload, invoice_payload


async def execute_action(action: StoredAction, invoices: InvoiceGateway) -> dict[str, object]:
    """Run one validated action for the caller that owns its execution claim."""
    parsed = parse_action(action.action_type, action.payload)
    try:
        if isinstance(parsed, CreateContactPayload):
            contact = await invoices.create_contact(parsed)
            return {"status": "executed", "contact": contact_payload(contact)}
        if isinstance(parsed, CreateInvoicePayload):
            invoice = await invoices.create_invoice(parsed)
            return {"status": "executed", "invoice": invoice_payload(invoice, include_lines=True)}
        if isinstance(parsed, UpdateInvoicePayload):
            invoice = await invoices.update_invoice(parsed)
            return {"status": "executed", "invoice": invoice_payload(invoice, include_lines=True)}
        if isinstance(parsed, VoidInvoicePayload):
            invoice = await invoices.void_invoice(parsed)
            return {"status": "executed", "invoice": invoice_payload(invoice, include_lines=True)}
    except ContactNotFoundError as error:
        raise ApiError(
            409,
            "Contact does not exist",
            f"No contact is named {error.name}.",
            False,
            "Choose an existing contact or create it first, then confirm a new invoice action.",
        ) from error
    except InvoiceNotFoundError as error:
        raise ApiError(
            404,
            "Invoice does not exist",
            f"No invoice is numbered {error.invoice_number}.",
            False,
            "Use find_invoices to get the invoice number, then propose the action again.",
        ) from error
    except InvoiceServiceError as error:
        raise ApiError(502 if error.outcome_unknown else 409, error.what, error.why, error.retryable, error.next_step, outcome_unknown=error.outcome_unknown) from error
    raise ApiError(422, "Unknown action type", action.action_type, False, "Propose a supported action.")


def failure_body(action_id: str, error: ApiError) -> dict[str, object]:
    """Shape a failed execution for the chat card and the stored result."""
    return {
        "action_id": action_id,
        "status": "unknown" if error.outcome_unknown else "failed",
        "what": error.what,
        "why": error.why,
        "retryable": error.retryable,
        "next_step": error.next_step,
    }
