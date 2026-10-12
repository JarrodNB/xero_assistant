"""Purpose: Verify partial edits preserve Xero accounting fields and validate line identity.

Public API:
- test_metadata_edits_leave_lines_untouched
- test_line_edits_preserve_accounting_metadata
- test_line_removal_and_addition_are_explicit
- test_invalid_line_edits_do_not_write
- test_editor_details_stay_out_of_model_payloads
- test_reference_clear_persists_through_api
- test_price_edit_without_tax_override_preserves_discounts
- test_all_original_lines_can_be_explicitly_replaced
- test_unsupported_lines_do_not_block_metadata_updates
- test_client_accounting_metadata_is_rejected
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.actions.payloads import UpdateInvoicePayload
from app.invoices.gateway import InvoiceServiceError
from app.invoices.records import InvoiceRecord, invoice_payload
from app.invoices.xero_service import XeroInvoiceService
from app.xero.mapping import map_invoice
from tests.conftest import sign_in

LINE_A = "11111111-1111-4111-8111-111111111111"
LINE_B = "22222222-2222-4222-8222-222222222222"


def _original() -> dict:
    """Return a taxed invoice with distinct accounts and tracking on its lines."""
    return {
        "InvoiceID": "invoice-id", "InvoiceNumber": "INV-1", "Type": "ACCREC", "Status": "AUTHORISED",
        "Contact": {"Name": "Review"}, "LineAmountTypes": "Inclusive", "Reference": "Original",
        "Total": 150, "AmountDue": 150, "CurrencyCode": "AUD",
        "LineItems": [
            {"LineItemID": LINE_A, "Description": "Work", "Quantity": 1, "UnitAmount": 100, "AccountCode": "201", "TaxType": "OUTPUT", "DiscountRate": 5, "TaxAmount": 9.09, "LineAmount": 95, "Tracking": [{"TrackingCategoryID": "region-id", "Name": "Region", "Option": "East"}]},
            {"LineItemID": LINE_B, "Description": "Parts", "Quantity": 1, "UnitAmount": 50, "AccountCode": "202", "TaxType": "NONE", "DiscountAmount": 2, "ItemCode": "PART"},
        ],
    }


def _lines() -> list[dict]:
    """Return only the permitted editable values and original line identities."""
    return [{"line_item_id": item["LineItemID"], "description": item["Description"], "quantity": item["Quantity"], "unit_amount": item["UnitAmount"]} for item in _original()["LineItems"]]


def _service(original: dict):
    """Build a service with captured writes and no external Xero access."""
    writes = []

    async def get(path, params=None):
        """Return the latest trusted invoice or deterministic defaults for new lines."""
        if path == "/Accounts":
            return {"Accounts": [{"Code": "200"}]}
        if path == "/TaxRates":
            return {"TaxRates": [{"Status": "ACTIVE", "CanApplyToRevenue": True, "TaxType": "NONE"}]}
        return {"Invoices": [deepcopy(original)]}

    async def post(path, payload):
        """Apply the partial update to the mock source of truth."""
        writes.append(deepcopy(payload))
        original.update(payload["Invoices"][0])
        return {"Invoices": [deepcopy(original)]}

    return XeroInvoiceService(SimpleNamespace(get=get, post=post)), writes


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [{"reference": "New"}, {"reference": ""}, {"due_date": "2026-11-01"}])
async def test_metadata_edits_leave_lines_untouched(fields) -> None:
    """Reference and date changes never send lines or their accounting defaults."""
    original = _original()
    original_lines = deepcopy(original["LineItems"])
    service, writes = _service(original)
    result = await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", **fields))
    assert "LineItems" not in writes[0]["Invoices"][0]
    assert "LineAmountTypes" not in writes[0]["Invoices"][0]
    assert original["LineItems"] == original_lines
    assert result.total == Decimal("150")
    if fields.get("reference") == "":
        assert result.reference is None


@pytest.mark.asyncio
@pytest.mark.parametrize("amount_type", ["Inclusive", "Exclusive", "NoTax"])
async def test_line_edits_preserve_accounting_metadata(amount_type) -> None:
    """Description edits retain tax overrides, discounts, identities, accounts, and tracking."""
    original = _original()
    original["LineAmountTypes"] = amount_type
    service, writes = _service(original)
    lines = _lines()
    lines[0]["description"] = "Updated work"
    await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", line_items=lines))
    sent = writes[0]["Invoices"][0]
    assert sent["LineAmountTypes"] == amount_type
    for index, line in enumerate(sent["LineItems"]):
        before = _original()["LineItems"][index]
        for key in ("LineItemID", "AccountCode", "TaxType", "TaxAmount", "DiscountRate", "DiscountAmount", "Tracking", "ItemCode"):
            if key in before:
                assert line[key] == before[key]
        assert "LineAmount" not in line
    assert sent["LineItems"][0]["Description"] == "Updated work"


@pytest.mark.asyncio
async def test_line_removal_and_addition_are_explicit() -> None:
    """Only new lines receive defaults; existing lines require explicit validated removals."""
    service, writes = _service(_original())
    await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", line_items=[_lines()[0], {"description": "New", "quantity": 1, "unit_amount": 10}], removed_line_item_ids=[LINE_B]))
    sent = writes[0]["Invoices"][0]["LineItems"]
    assert sent[0]["AccountCode"] == "201"
    assert sent[0]["TaxType"] == "OUTPUT"
    assert sent[1]["AccountCode"] == "200"
    assert sent[1]["TaxType"] == "NONE"
    assert "LineItemID" not in sent[1]
    assert len(sent) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["foreign_id", "missing_id", "duplicate_id", "implicit_removal", "remove_kept", "duplicate_removal", "explicit_tax_money", "unsupported_field", "missing_amount_type", "both_discounts"])
async def test_invalid_line_edits_do_not_write(case) -> None:
    """Ambiguous identity, unsupported metadata, and unsafe tax edits fail before writing."""
    original, lines, removed = _original(), _lines(), []
    if case == "foreign_id": lines[0]["line_item_id"] = str(uuid4())
    if case == "missing_id": lines[0].pop("line_item_id")
    if case == "duplicate_id": lines[1]["line_item_id"] = LINE_A
    if case == "implicit_removal": lines.pop()
    if case == "remove_kept": removed = [LINE_A]
    if case == "duplicate_removal": lines.pop(); removed = [LINE_B, LINE_B]
    if case == "explicit_tax_money": lines[0]["quantity"] = 2
    if case == "unsupported_field": original["LineItems"][0]["FutureAccountingField"] = "important"
    if case == "missing_amount_type": original.pop("LineAmountTypes")
    if case == "both_discounts": original["LineItems"][0]["DiscountAmount"] = 5
    service, writes = _service(original)
    with pytest.raises(InvoiceServiceError):
        await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", line_items=lines, removed_line_item_ids=removed))
    assert writes == []


def test_editor_details_stay_out_of_model_payloads() -> None:
    """Editor identities and capabilities appear only in HTTP editor serialization."""
    invoice = map_invoice(_original())
    model = invoice_payload(invoice, include_lines=True)
    editor = invoice_payload(invoice, include_lines=True, include_edit_details=True)
    assert "line_item_id" not in model["line_items"][0]
    assert editor["line_items"][0]["line_item_id"] == LINE_A
    assert editor["line_items"][0]["has_explicit_tax"] is True
    assert editor["line_editing_supported"] is True


def test_reference_clear_persists_through_api(api) -> None:
    """Clearing a reference is distinguishable from omitting it across save and reload."""
    client, gateway = api
    sign_in(client)
    gateway.invoices.append(InvoiceRecord(invoice_number="INV-1", contact_name="Review", status="AUTHORISED", issued_on=date(2026, 10, 12), due_date=date(2026, 11, 1), total=Decimal("100"), amount_due=Decimal("100"), currency="AUD", reference="Original"))
    changed = client.put("/invoices/INV-1", json={"invoice_number": "INV-1", "due_date": "2026-11-02"})
    assert changed.status_code == 200
    assert client.get("/invoices/INV-1").json()["invoice"]["reference"] == "Original"
    cleared = client.put("/invoices/INV-1", json={"invoice_number": "INV-1", "reference": ""})
    assert cleared.status_code == 200
    assert not client.get("/invoices/INV-1").json()["invoice"]["reference"]


@pytest.mark.asyncio
async def test_price_edit_without_tax_override_preserves_discounts() -> None:
    """Permitted amount edits keep existing account, tax type, and discount behavior."""
    service, writes = _service(_original())
    lines = _lines()
    lines[1]["unit_amount"] = 60
    await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", line_items=lines))
    changed = writes[0]["Invoices"][0]["LineItems"][1]
    assert changed["UnitAmount"] == "60"
    assert changed["AccountCode"] == "202"
    assert changed["TaxType"] == "NONE"
    assert changed["DiscountAmount"] == 2


@pytest.mark.asyncio
async def test_all_original_lines_can_be_explicitly_replaced() -> None:
    """A complete intentional replacement names every removed original line."""
    service, writes = _service(_original())
    await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", line_items=[{"description": "New", "quantity": 1, "unit_amount": 20}], removed_line_item_ids=[LINE_A, LINE_B]))
    assert len(writes[0]["Invoices"][0]["LineItems"]) == 1
    assert writes[0]["Invoices"][0]["LineItems"][0]["AccountCode"] == "200"


@pytest.mark.asyncio
async def test_unsupported_lines_do_not_block_metadata_updates() -> None:
    """Unsupported future accounting fields survive a metadata-only write unchanged."""
    original = _original()
    original["LineItems"][0]["FutureAccountingField"] = "keep"
    service, writes = _service(original)
    assert map_invoice(original).line_editing_supported is False
    await service.update_invoice(UpdateInvoicePayload(invoice_number="INV-1", reference="Safe update"))
    assert "LineItems" not in writes[0]["Invoices"][0]
    assert original["LineItems"][0]["FutureAccountingField"] == "keep"


def test_client_accounting_metadata_is_rejected() -> None:
    """The client cannot supply account or tax fields instead of server-owned values."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UpdateInvoicePayload(invoice_number="INV-1", line_items=[{**_lines()[0], "AccountCode": "999"}])
