"""Purpose: Offline currency, completeness, filter, HTTP and MCP regressions.

Public API:
- pytest regression cases
"""

from datetime import date
from decimal import Decimal

import pytest
from fastmcp import Client

from app.invoices.gateway import InvoiceReadResult, InvoiceServiceError
from app.invoices.records import InvoiceRecord
from app.invoices.summary import summarize_invoice_records, compare_invoice_periods, summary_payload, comparison_payload
from app.invoices.xero_service import XeroInvoiceService
from app.mcp_server.server import build_mcp_server
from app.runtime import AppServices, current_services
from tests.conftest import sign_in
from tests.fakes import FakeInvoiceGateway


def invoice(currency="AUD", issued=date(2026, 1, 15)):
    """Return a synthetic authorised invoice with a native-currency balance."""
    return InvoiceRecord("INV-1", "Example", "AUTHORISED", issued, date(2026, 1, 20),
                         Decimal("100"), Decimal("100"), currency, None)


def test_mixed_currencies_and_empty_summary():
    """Currency groups never expose an unlabeled mixed total or invent empty currency."""
    payload = summary_payload(summarize_invoice_records([invoice("USD"), invoice("AUD")], date(2026, 2, 1)))
    assert payload["complete"] is True
    assert payload["schema_version"] == "2"
    assert payload["invoice_count"] == 2
    assert "invoice_total" not in payload
    assert [(row["currency"], row["invoice_total"], row["overdue_total"]) for row in payload["currencies"]] == [
        ("AUD", 100, 100), ("USD", 100, 100)]
    assert summary_payload(summarize_invoice_records([], date.today()))["currencies"] == []


def test_comparison_aligns_missing_currencies_and_empty():
    """A currency occurring in one period gets zero only in the other period."""
    dates = (date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 28))
    result = comparison_payload(compare_invoice_periods([invoice("USD"), invoice("AUD", date(2026, 2, 15))], *dates))
    assert result["currencies"] == [
        {"currency": "AUD", "period_a_total": 0, "period_b_total": 100, "difference": 100},
        {"currency": "USD", "period_a_total": 100, "period_b_total": 0, "difference": -100}]
    assert comparison_payload(compare_invoice_periods([], *dates))["currencies"] == []


def test_unknown_currency_and_reversed_ranges_fail():
    """Invalid currency or date ordering must not produce plausible financial totals."""
    with pytest.raises(ValueError, match="currency"):
        summarize_invoice_records([invoice("")], date.today())
    with pytest.raises(ValueError, match="start date"):
        compare_invoice_periods([], date(2026, 2, 1), date(2026, 1, 1), date(2026, 1, 1), date(2026, 1, 31))


class PagedClient:
    """Xero stand-in with fixed-size pages and request capture."""

    def __init__(self, count):
        """Store a synthetic row count and empty request log."""
        self.count = count
        self.calls = []

    async def get(self, path, params=None):
        """Return deterministic invoice pages or one matching contact."""
        self.calls.append((path, params))
        if path == "/Contacts":
            return {"Contacts": [{"ContactID": "contact-1", "Name": "Example"}]}
        offset = (params["page"] - 1) * 100
        count = max(0, min(100, self.count - offset))
        return {"Invoices": [{"InvoiceNumber": f"INV-{offset + index}", "CurrencyCode": "AUD",
                              "Contact": {"Name": "Example"}, "Total": 100, "AmountDue": 100,
                              "Status": "AUTHORISED", "DateString": "2026-01-15"} for index in range(count)]}


@pytest.mark.asyncio
@pytest.mark.parametrize("count,complete,pages", [(1999, True, 20), (2000, True, 21), (2001, False, 21)])
async def test_below_exact_and_above_cap(count, complete, pages):
    """One bounded lookahead distinguishes exact-cap reads from truncated reads."""
    client = PagedClient(count)
    service = XeroInvoiceService(client)
    result = await service.find_invoices(None, None, None, None)
    assert result.complete is complete
    assert len(result.invoices) == min(count, 2000)
    assert result.scanned_count == min(count, 2000)
    assert len(client.calls) == pages
    if complete:
        assert len(result.require_complete()) == count
    else:
        with pytest.raises(InvoiceServiceError, match="incomplete"):
            result.require_complete()
        with pytest.raises(InvoiceServiceError, match="incomplete"):
            await service.summarize_invoices(None, None, None, None, date.today())
        with pytest.raises(InvoiceServiceError, match="incomplete"):
            await service.compare_invoice_totals(date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), date(2026, 2, 28))


@pytest.mark.asyncio
async def test_filters_applied_before_invoice_budget():
    """Contact IDs, sales type, status and dates are sent to Xero before pagination."""
    client = PagedClient(1)
    service = XeroInvoiceService(client)
    await service.find_invoices("Example", "AUTHORISED", date(2026, 1, 1), date(2026, 1, 31))
    params = client.calls[-1][1]
    assert params["ContactIDs"] == "contact-1"
    assert 'Type=="ACCREC"' in params["where"]
    assert 'Status=="AUTHORISED"' in params["where"]
    assert "Date>=DateTime(2026,1,1)" in params["where"]
    assert "Date<=DateTime(2026,1,31)" in params["where"]
    client.calls.clear()
    with pytest.raises(InvoiceServiceError, match="Date range"):
        await service.find_invoices(None, None, date(2026, 2, 1), date(2026, 1, 1))
    assert client.calls == []


class PartialGateway(FakeInvoiceGateway):
    """Expose an empty filtered subset from an incomplete bounded read."""

    async def find_invoices(self, *args):
        """Return partial emptiness without establishing absence."""
        return InvoiceReadResult([], False, 2000)


def test_http_currency_contract_and_date_validation(api):
    """HTTP exposes v2 totals and rejects reversed ranges before gateway reads."""
    client, fake = api
    sign_in(client)
    fake.invoices = [invoice("USD"), invoice("AUD")]
    response = client.get("/invoice-summary")
    assert response.status_code == 200
    assert [group["currency"] for group in response.json()["currencies"]] == ["AUD", "USD"]
    for path in ("/invoices", "/invoice-summary"):
        response = client.get(path, params={"date_from": "2026-02-01", "date_to": "2026-01-01"})
        assert response.status_code == 422
    assert client.get("/invoices").json()["complete"] is True


@pytest.mark.asyncio
async def test_partial_mcp_list_cannot_establish_absence_or_totals(api):
    """MCP lists identify partial emptiness and summaries fail closed."""
    client, _ = api
    fake = PartialGateway()
    services = client.app.state.services
    token = current_services.set(AppServices(invoices=fake, actions=services.actions))
    try:
        async with Client(build_mcp_server()) as mcp:
            listing = (await mcp.call_tool("find_invoices", {})).structured_content["result"]
            assert listing["complete"] is False
            assert listing["invoices"] == []
            assert "Narrow" in listing["next_step"]
            summary = (await mcp.call_tool("summarize_invoices", {})).structured_content["result"]
            assert summary["ok"] is False
            assert "currencies" not in summary
    finally:
        current_services.reset(token)

@pytest.mark.parametrize("scenario,answer,expected", [
    ("mixed", "AUD 100.00 and USD 100.00", True),
    ("mixed", "The total is 200", False),
    ("mixed", "AUD 100 and USD 100, combined 200", False),
    ("empty", "No matching invoices.", True),
    ("empty", "No invoices. AUD 0", False),
    ("truncated", "Results are incomplete; narrow the date filters.", True),
    ("truncated", "No matching invoices; narrow filters for partial results.", False),
    ("truncated", "The balance is 0, partial results; narrow filters.", False),
])
def test_financial_answer_evaluator_does_not_trust_trace(scenario, answer, expected):
    """Correct tool facts cannot compensate for misleading answer text."""
    from types import SimpleNamespace
    from evals.invoices.evaluators import FinancialAnswer
    from evals.trace import TRACE_HEADING
    context = SimpleNamespace(metadata={"financial_scenario": scenario},
                              output=answer + TRACE_HEADING + 'result summarize_invoices AUD 100 USD 100')
    assert FinancialAnswer().evaluate(context) is expected


@pytest.mark.asyncio
async def test_malformed_read_is_not_empty():
    """Missing page arrays fail rather than falsely establishing no invoices."""
    client = PagedClient(0)

    async def malformed(*args):
        """Return a syntactically valid but incomplete provider envelope."""
        return {}

    client.get = malformed
    with pytest.raises(InvoiceServiceError, match="invalid"):
        await XeroInvoiceService(client).find_invoices(None, None, None, None)


@pytest.mark.asyncio
async def test_contact_search_cannot_hide_truncation():
    """An over-cap contact lookup fails before an invoice absence claim is possible."""
    client = PagedClient(0)

    async def contacts(path, params):
        """Return full contact pages plus one bounded lookahead record."""
        return {"Contacts": [{"ContactID": "contact-1", "Name": "Example"}] * (100 if params["page"] <= 20 else 1)}

    client.get = contacts
    with pytest.raises(InvoiceServiceError, match="incomplete"):
        await XeroInvoiceService(client).find_invoices("Example", None, None, None)


@pytest.mark.asyncio
async def test_versioned_mcp_schemas_are_discoverable():
    """Clients discover currency and completeness fields from typed v2 output schemas."""
    import json
    async with Client(build_mcp_server()) as mcp:
        tools = {tool.name: tool for tool in await mcp.list_tools()}
    for name in ("find_invoices", "summarize_invoices", "compare_invoice_totals"):
        schema = json.dumps(tools[name].output_schema)
        assert "schema_version" in schema
        assert "complete" in schema
        assert '"2"' in schema
    assert "currencies" in json.dumps(tools["summarize_invoices"].output_schema)


def test_http_partial_results_and_aggregate_rejection(api):
    """HTTP carries partial metadata and refuses both financial aggregates."""
    client, _ = api
    sign_in(client)
    client.app.state.services.invoices = PartialGateway()
    listing = client.get("/invoices")
    assert listing.status_code == 200
    assert listing.json()["complete"] is False
    assert listing.json()["invoices"] == []
    summary = client.get("/invoice-summary")
    assert summary.status_code == 409
    assert "currencies" not in summary.json()
    comparison = client.get("/invoice-comparison", params={
        "period_a_start": "2026-01-01", "period_a_end": "2026-01-31",
        "period_b_start": "2026-02-01", "period_b_end": "2026-02-28"})
    assert comparison.status_code == 409

@pytest.mark.asyncio
async def test_comparison_queries_only_requested_windows_and_deduplicates_overlap():
    """Gap invoices cannot consume period budgets, and overlaps are counted once."""
    client = PagedClient(1)
    service = XeroInvoiceService(client)
    result = await service.compare_invoice_totals(date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 10), date(2026, 1, 20))
    assert len(client.calls) == 2
    assert "Date>=DateTime(2026,1,10)" in client.calls[1][1]["where"]
    assert result.currencies[0].period_a_total == Decimal("100")
    assert result.currencies[0].period_b_total == Decimal("100")
    client.calls.clear()
    await service.compare_invoice_totals(date(2026, 1, 1), date(2026, 1, 31), date(2026, 3, 1), date(2026, 3, 31))
    assert "Date<=DateTime(2026,1,31)" in client.calls[0][1]["where"]
    assert "Date>=DateTime(2026,3,1)" in client.calls[1][1]["where"]
    client.calls.clear()
    await service.compare_invoice_totals(date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1), date(2026, 1, 31))
    assert len(client.calls) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize("count,complete", [(1999, True), (2000, True), (2001, False)])
async def test_contact_list_cap_uses_lookahead(count, complete):
    """Contact lists distinguish exact caps and refuse silent truncation."""
    client = PagedClient(0)
    pages = []

    async def contacts(path, params):
        """Return a controlled number of paged contacts."""
        pages.append(params["page"])
        size = max(0, min(100, count - (params["page"] - 1) * 100))
        return {"Contacts": [{"Name": "Synthetic"}] * size}

    client.get = contacts
    if complete:
        assert len(await XeroInvoiceService(client).list_contacts()) == count
    else:
        with pytest.raises(InvoiceServiceError, match="incomplete"):
            await XeroInvoiceService(client).list_contacts()
    assert max(pages) <= 21


@pytest.mark.asyncio
async def test_mcp_currency_summary_and_comparison(api):
    """Actual MCP output contracts preserve grouped and aligned amounts."""
    client, fake = api
    fake.invoices = [invoice("USD"), invoice("AUD", date(2026, 2, 15))]
    token = current_services.set(client.app.state.services)
    try:
        async with Client(build_mcp_server()) as mcp:
            summary = (await mcp.call_tool("summarize_invoices", {})).structured_content["result"]
            assert [row["currency"] for row in summary["currencies"]] == ["AUD", "USD"]
            assert "unpaid_total" not in summary
            comparison = (await mcp.call_tool("compare_invoice_totals", {
                "period_a_start": "2026-01-01", "period_a_end": "2026-01-31",
                "period_b_start": "2026-02-01", "period_b_end": "2026-02-28"})).structured_content["result"]
            assert comparison["currencies"][0]["period_a_total"] == 0
            assert comparison["currencies"][1]["period_b_total"] == 0
            invalid = (await mcp.call_tool("find_invoices", {
                "date_from": "2026-02-01", "date_to": "2026-01-01"})).structured_content["result"]
            assert invalid["ok"] is False
    finally:
        current_services.reset(token)

@pytest.mark.asyncio
async def test_invalid_status_and_missing_contact_identity_fail_safely():
    """Validation cannot be bypassed by absent contacts or malformed identity data."""
    client = PagedClient(0)
    service = XeroInvoiceService(client)
    with pytest.raises(InvoiceServiceError, match="status is invalid"):
        await service.find_invoices("Example", "INVALID", None, None)
    assert client.calls == []

    async def missing_identity(path, params):
        """Return a matching contact without its authoritative ID."""
        return {"Contacts": [{"Name": "Example"}]}

    client.get = missing_identity
    with pytest.raises(InvoiceServiceError, match="contact response is invalid"):
        await service.find_invoices("Example", None, None, None)
