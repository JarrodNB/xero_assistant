"""Purpose: Preserve trusted Xero line metadata while validating explicit editor changes.

Public API:
- can_edit_lines
- merge_invoice_lines
"""

from copy import deepcopy
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.actions.payloads import MAX_INVOICE_SUBTOTAL, MAX_LINE_ITEMS, UpdateInvoicePayload, UpdateLineItemPayload
from app.invoices.gateway import InvoiceServiceError

PRESERVED_FIELDS = frozenset({
    "LineItemID", "Description", "Quantity", "UnitAmount", "AccountCode", "TaxType",
    "Tracking", "ItemCode", "DiscountRate", "DiscountAmount", "TaxAmount",
})
COMPUTED_FIELDS = frozenset({"LineAmount", "ValidationErrors"})
AMOUNT_TYPES = frozenset({"Inclusive", "Exclusive", "NoTax"})


def _unsupported(why: str) -> InvoiceServiceError:
    """Explain why an edit is rejected before any accounting write."""
    return InvoiceServiceError("Invoice lines cannot be edited safely", why, False, "Reload the invoice; use Xero for unsupported line or tax changes.")


def _original_lines(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate that every original line has a unique identity and supported accounting data."""
    if raw.get("LineAmountTypes") not in AMOUNT_TYPES:
        raise _unsupported("The invoice amount convention is unsupported.")
    if len(raw.get("LineItems") or []) > MAX_LINE_ITEMS:
        raise _unsupported("The invoice exceeds the editor's line-count limit.")
    lines: dict[str, dict[str, Any]] = {}
    subtotal = Decimal("0")
    for item in raw.get("LineItems") or []:
        if not isinstance(item, dict) or set(item) - PRESERVED_FIELDS - COMPUTED_FIELDS:
            raise _unsupported("The invoice contains line fields this editor cannot preserve.")
        try:
            identity = str(UUID(str(item.get("LineItemID"))))
            UpdateLineItemPayload.model_validate({
                "description": item.get("Description"), "quantity": item.get("Quantity"),
                "unit_amount": item.get("UnitAmount"), "line_item_id": identity,
            })
        except (ValueError, ValidationError) as error:
            raise _unsupported("The invoice contains unsupported line identifiers or numeric values.") from error
        if identity in lines:
            raise _unsupported("The invoice contains duplicate line identifiers.")
        if item.get("DiscountRate") and item.get("DiscountAmount"):
            raise _unsupported("The invoice exposes both percentage and amount discounts on a line.")
        subtotal += Decimal(str(item["Quantity"])) * Decimal(str(item["UnitAmount"]))
        if subtotal > MAX_INVOICE_SUBTOTAL:
            raise _unsupported("The invoice exceeds the editor's amount limit.")
        lines[identity] = item
    return lines


def can_edit_lines(raw: dict[str, Any]) -> bool:
    """Report whether the editor can round-trip these lines without losing accounting fields."""
    try:
        _original_lines(raw)
    except InvoiceServiceError:
        return False
    return True


def merge_invoice_lines(raw: dict[str, Any], payload: UpdateInvoicePayload) -> list[dict[str, Any]]:
    """Merge a complete replacement list, validating kept and explicitly removed line identities."""
    originals = _original_lines(raw)
    removed = [str(identity) for identity in payload.removed_line_item_ids]
    kept = [str(line.line_item_id) for line in payload.line_items or [] if line.line_item_id is not None]
    if len(set(removed)) != len(removed) or len(set(kept)) != len(kept) or set(removed) & set(kept):
        raise _unsupported("A line cannot be duplicated or both kept and removed.")
    if set(kept) | set(removed) != set(originals):
        raise _unsupported("Every existing line must be retained by its id or explicitly removed; ids must belong to this invoice.")
    merged: list[dict[str, Any]] = []
    for line in payload.line_items or []:
        values = {"Description": line.description, "Quantity": format(line.quantity, "f"), "UnitAmount": format(line.unit_amount, "f")}
        if line.line_item_id is None:
            merged.append(values)
            continue
        original = originals[str(line.line_item_id)]
        monetary_change = Decimal(str(original["Quantity"])) != line.quantity or Decimal(str(original["UnitAmount"])) != line.unit_amount
        if monetary_change and original.get("TaxAmount") is not None:
            raise _unsupported("Amounts on a line with an explicit tax amount must be changed in Xero; this editor cannot distinguish a tax override from a calculated tax.")
        preserved = {key: deepcopy(value) for key, value in original.items() if key in PRESERVED_FIELDS}
        preserved.update(values)
        merged.append(preserved)
    return merged
