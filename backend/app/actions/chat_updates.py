"""Purpose: Resolve model-visible invoice line values to private Xero identities.

Public API:
- resolve_chat_update
"""

from typing import Any
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.actions.payloads import LineItemPayload, MAX_LINE_ITEMS, UpdateInvoicePayload
from app.errors import ApiError
from app.invoices.gateway import InvoiceGateway, InvoiceNotFoundError, InvoiceServiceError


class OriginalLine(LineItemPayload):
    """An exact original-value selector with no accepted identity or accounting fields."""

    model_config = ConfigDict(extra="forbid")


class ChatLineUpdate(LineItemPayload):
    """Editable values with an exact original-value selector instead of an internal id."""

    model_config = ConfigDict(extra="forbid")
    original_line: OriginalLine | None = None


class ChatInvoiceUpdate(BaseModel):
    """Model-facing update schema that never accepts internal identities."""

    model_config = ConfigDict(extra="forbid")
    invoice_number: str = Field(min_length=1, max_length=50)
    contact_name: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    line_items: list[ChatLineUpdate] | None = Field(default=None, min_length=1, max_length=MAX_LINE_ITEMS)
    removed_lines: list[OriginalLine] = Field(default_factory=list, max_length=MAX_LINE_ITEMS)


async def resolve_chat_update(payload: dict[str, Any], invoices: InvoiceGateway) -> dict[str, Any]:
    """Bind unique original-value selectors to private ids before storing a proposal."""
    next_step = "Use get_invoice first. Identify kept or removed lines by exact original description, quantity, and unit_amount; use the invoice editor for ambiguous lines."
    try:
        parsed = ChatInvoiceUpdate.model_validate(payload)
        if parsed.line_items is None and parsed.removed_lines:
            raise ValueError("Line removals require the complete remaining line list.")
        resolved = parsed.model_dump(mode="json", exclude={"line_items", "removed_lines"}, exclude_unset=True)
        if parsed.line_items is not None:
            invoice = await invoices.get_invoice(parsed.invoice_number)
            if not invoice.line_editing_supported:
                raise ValueError("These invoice lines require editing in Xero.")

            def identity(selector: LineItemPayload) -> str:
                """Require exactly one trusted line matching all original editable values."""
                matches = [line for line in invoice.line_items if
                    (line.description, line.quantity, line.unit_amount) ==
                    (selector.description, selector.quantity, selector.unit_amount)]
                if len(matches) != 1 or not matches[0].line_item_id:
                    raise ValueError("An original line is missing, changed, or ambiguous; reload it before proposing.")
                return matches[0].line_item_id

            resolved["line_items"] = [
                {**line.model_dump(mode="json", exclude={"original_line"}),
                 **({"line_item_id": identity(line.original_line)} if line.original_line else {})}
                for line in parsed.line_items
            ]
            removed = [identity(line) for line in parsed.removed_lines]
            kept = [line["line_item_id"] for line in resolved["line_items"] if "line_item_id" in line]
            if len(set(kept + removed)) != len(kept + removed) or set(kept + removed) != {line.line_item_id for line in invoice.line_items}:
                raise ValueError("Retain every original line once or explicitly list it in removed_lines.")
            resolved["removed_line_item_ids"] = removed
        return UpdateInvoicePayload.model_validate(resolved).model_dump(mode="json")
    except InvoiceNotFoundError as error:
        raise ApiError(404, "Invoice does not exist", "The requested invoice could not be found.", False, next_step) from error
    except InvoiceServiceError as error:
        raise ApiError(409, error.what, error.why, error.retryable, error.next_step) from error
    except (ValueError, ValidationError) as error:
        why = "Chat invoice fields or original line selectors are invalid." if isinstance(error, ValidationError) else str(error)
        raise ApiError(422, "Invoice update cannot be proposed", why, False, next_step) from error
