"""Purpose: Validate write payloads before they are stored or executed.

Public API:
- CreateContactPayload
- LineItemPayload
- CreateInvoicePayload
- UpdateInvoicePayload
- VoidInvoicePayload
- parse_action
- summarize_action
"""

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.errors import ApiError

ActionType = Literal["create_contact", "create_invoice", "update_invoice", "void_invoice"]
ACTION_TYPES = ("create_contact", "create_invoice", "update_invoice", "void_invoice")


class LineItemPayload(BaseModel):
    """One sales line on a proposed invoice."""

    description: str = Field(min_length=1, max_length=4000)
    quantity: float = Field(gt=0)
    unit_amount: float = Field(gt=0)


class CreateContactPayload(BaseModel):
    """Fields required to create a contact."""

    name: str = Field(min_length=1, max_length=255)
    email: str | None = None


class CreateInvoicePayload(BaseModel):
    """Fields required to create an authorised sales invoice."""

    contact_name: str = Field(min_length=1, max_length=255)
    line_items: list[LineItemPayload] = Field(min_length=1)
    reference: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    def due_on(self, today: date) -> date:
        """Return the requested due date, or 14 days from today."""
        return self.due_date or today + timedelta(days=14)


class UpdateInvoicePayload(BaseModel):
    """Fields that may change on an existing invoice."""

    invoice_number: str = Field(min_length=1, max_length=50)
    contact_name: str | None = Field(default=None, max_length=255)
    line_items: list[LineItemPayload] | None = None
    reference: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    def has_change(self) -> bool:
        """Return whether any editable field was provided."""
        return any(
            value is not None
            for value in (self.contact_name, self.line_items, self.reference, self.due_date)
        )


class VoidInvoicePayload(BaseModel):
    """The invoice number to void."""

    invoice_number: str = Field(min_length=1, max_length=50)


def parse_action(action_type: str, payload: dict[str, Any]) -> CreateContactPayload | CreateInvoicePayload | UpdateInvoicePayload | VoidInvoicePayload:
    """Validate a payload for one action type."""
    if action_type not in ACTION_TYPES:
        raise ApiError(
            422,
            "Unknown action type",
            f"{action_type} is not a supported write.",
            False,
            "Use create_contact, create_invoice, update_invoice, or void_invoice.",
        )
    model = {
        "create_contact": CreateContactPayload,
        "create_invoice": CreateInvoicePayload,
        "update_invoice": UpdateInvoicePayload,
        "void_invoice": VoidInvoicePayload,
    }[action_type]
    try:
        parsed = model.model_validate(payload)
    except ValidationError as error:
        raise ApiError(
            422,
            "Action payload is invalid",
            error.errors()[0]["msg"],
            False,
            "Correct the payload fields and propose the action again.",
        ) from error
    if isinstance(parsed, UpdateInvoicePayload) and not parsed.has_change():
        raise ApiError(
            422,
            "Invoice update is empty",
            "No invoice fields were provided to change.",
            False,
            "Include a contact name, line items, reference, or due date.",
        )
    return parsed


def summarize_action(action_type: str, payload: dict[str, Any]) -> str:
    """Build a short sentence a person can confirm."""
    parsed = parse_action(action_type, payload)
    if isinstance(parsed, CreateContactPayload):
        return f"Create contact {parsed.name}."
    if isinstance(parsed, CreateInvoicePayload):
        amount = sum(item.quantity * item.unit_amount for item in parsed.line_items)
        return f"Create an authorised invoice for {parsed.contact_name} for {amount:.2f}."
    if isinstance(parsed, UpdateInvoicePayload):
        return f"Update invoice {parsed.invoice_number}."
    return f"Void invoice {parsed.invoice_number}."
