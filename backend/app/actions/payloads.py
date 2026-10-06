"""Purpose: Validate write payloads before they are stored or executed.

Public API:
- CreateContactPayload
- LineItemPayload
- CreateInvoicePayload
- UpdateInvoicePayload
- VoidInvoicePayload
- parse_action
- summarize_action
- apply_optional_overrides
"""

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.errors import ApiError

ActionType = Literal["create_contact", "create_invoice", "update_invoice", "void_invoice"]
ACTION_TYPES = ("create_contact", "create_invoice", "update_invoice", "void_invoice")
OPTIONAL_CONFIRM_FIELDS: dict[str, tuple[str, ...]] = {
    "create_contact": ("email",),
    "create_invoice": ("reference", "due_date"),
}


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
        if parsed.email:
            return f"Create contact {parsed.name} with email {parsed.email}."
        return f"Create contact {parsed.name}."
    if isinstance(parsed, CreateInvoicePayload):
        amount = sum(item.quantity * item.unit_amount for item in parsed.line_items)
        sentence = f"Create an authorised invoice for {parsed.contact_name} for {amount:.2f}"
        extras: list[str] = []
        if parsed.reference:
            extras.append(f"reference {parsed.reference}")
        if parsed.due_date:
            extras.append(f"due {parsed.due_date.isoformat()}")
        if extras:
            return sentence + " with " + " and ".join(extras) + "."
        return sentence + "."
    if isinstance(parsed, UpdateInvoicePayload):
        return f"Update invoice {parsed.invoice_number}."
    return f"Void invoice {parsed.invoice_number}."


def apply_optional_overrides(
    action_type: str,
    payload: dict[str, Any],
    overrides: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Merge confirm-time optional fields and return the payload and summary."""
    allowed = OPTIONAL_CONFIRM_FIELDS.get(action_type, ())
    blocked = sorted(key for key in overrides if key not in allowed)
    if blocked:
        names = ", ".join(blocked)
        raise ApiError(
            422,
            "Confirm cannot change required fields",
            f"{names} cannot be changed on confirm.",
            False,
            "Change only email, reference, or due date, or ask the assistant to propose again.",
        )
    merged = dict(payload)
    for key in allowed:
        if key not in overrides:
            continue
        merged[key] = _blank_to_none(overrides[key])
    parsed = parse_action(action_type, merged)
    stored = parsed.model_dump(mode="json")
    return stored, summarize_action(action_type, stored)


def _blank_to_none(value: Any) -> Any:
    """Treat a blank string as an omitted optional field."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value
