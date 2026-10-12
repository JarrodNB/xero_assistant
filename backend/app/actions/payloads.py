"""Purpose: Validate write payloads before they are stored or executed.

Public API:
- MAX_LINE_ITEMS
- MAX_QUANTITY
- MAX_UNIT_AMOUNT
- MAX_INVOICE_SUBTOTAL
- CreateContactPayload
- LineItemPayload
- UpdateLineItemPayload
- CreateInvoicePayload
- UpdateInvoicePayload
- VoidInvoicePayload
- parse_action
- summarize_action
- apply_optional_overrides
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.errors import ApiError

ActionType = Literal["create_contact", "create_invoice", "update_invoice", "void_invoice"]
ACTION_TYPES = ("create_contact", "create_invoice", "update_invoice", "void_invoice")
MAX_LINE_ITEMS = 100
MAX_QUANTITY = Decimal("99999999.9999")
MAX_UNIT_AMOUNT = Decimal("999999999999.99")
MAX_INVOICE_SUBTOTAL = Decimal("999999999999.99")
Quantity = Annotated[
    Decimal,
    Field(gt=0, le=MAX_QUANTITY, max_digits=12, decimal_places=4, allow_inf_nan=False),
]
UnitAmount = Annotated[
    Decimal,
    Field(gt=0, le=MAX_UNIT_AMOUNT, max_digits=14, decimal_places=2, allow_inf_nan=False),
]
OPTIONAL_CONFIRM_FIELDS: dict[str, tuple[str, ...]] = {
    "create_contact": ("email",),
    "create_invoice": ("reference", "due_date"),
}


class LineItemPayload(BaseModel):
    """One sales line on a proposed invoice."""

    description: str = Field(min_length=1, max_length=4000)
    quantity: Quantity
    unit_amount: UnitAmount


class CreateContactPayload(BaseModel):
    """Fields required to create a contact."""

    name: str = Field(min_length=1, max_length=255)
    email: str | None = None


class CreateInvoicePayload(BaseModel):
    """Fields required to create an authorised sales invoice."""

    contact_name: str = Field(min_length=1, max_length=255)
    line_items: list[LineItemPayload] = Field(min_length=1, max_length=MAX_LINE_ITEMS)
    reference: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    def due_on(self, today: date) -> date:
        """Return the requested due date, or 14 days from today."""
        return self.due_date or today + timedelta(days=14)

    @model_validator(mode="after")
    def subtotal_is_safe(self) -> Self:
        """Reject an invoice whose exact pre-tax total exceeds the application limit."""
        _validate_subtotal(self.line_items)
        return self


class UpdateLineItemPayload(LineItemPayload):
    """Editable line values with an optional identity scoped to the current invoice."""

    model_config = ConfigDict(extra="forbid")
    line_item_id: UUID | None = None


class UpdateInvoicePayload(BaseModel):
    """Fields that may change on an existing invoice."""

    invoice_number: str = Field(min_length=1, max_length=50)
    contact_name: str | None = Field(default=None, max_length=255)
    line_items: list[UpdateLineItemPayload] | None = Field(default=None, min_length=1, max_length=MAX_LINE_ITEMS)
    removed_line_item_ids: list[UUID] = Field(default_factory=list, max_length=MAX_LINE_ITEMS)
    reference: str | None = Field(default=None, max_length=255)
    due_date: date | None = None

    def has_change(self) -> bool:
        """Return whether any editable field was provided."""
        return any(
            value is not None
            for value in (self.contact_name, self.line_items, self.reference, self.due_date)
        )

    @model_validator(mode="after")
    def subtotal_is_safe(self) -> Self:
        """Reject replacement lines whose exact pre-tax total exceeds the application limit."""
        if self.line_items is not None:
            _validate_subtotal(self.line_items)
        elif self.removed_line_item_ids:
            raise ValueError("Line removals require the complete remaining line list.")
        return self


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
            _validation_next_step(action_type),
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


def _validation_next_step(action_type: str) -> str:
    """Return action-specific guidance after payload validation fails."""
    if action_type in ("create_invoice", "update_invoice"):
        return (
            "Correct the invalid field. Use at most 100 lines, quantity from 0.0001 to 99999999.9999 with up to "
            "four decimal places, unit amount from 0.01 to 999999999999.99 with up to two decimal places, and a "
            "subtotal at most 999999999999.99; then propose the action again."
        )
    return "Correct the invalid payload field and propose the action again."


def _validate_subtotal(line_items: list[LineItemPayload]) -> None:
    """Reject an exact line-item subtotal above the safe invoice limit."""
    subtotal = sum((item.quantity * item.unit_amount for item in line_items), Decimal("0"))
    if subtotal > MAX_INVOICE_SUBTOTAL:
        raise ValueError(f"invoice subtotal must be at most {MAX_INVOICE_SUBTOTAL}")
