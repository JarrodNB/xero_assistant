"""Purpose: Verify authenticated, bounded, source-backed performance reports.

Public API:
- Offline pytest report cases
"""

import os
import asyncio
import gzip
import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.xero.connection_store import XeroConnection
from tests.conftest import sign_in
from tests.fakes import FakeInvoiceGateway


def report_body() -> dict:
    """Build a labelled synthetic standard-layout report with private account ids."""
    return {"Reports": [{"ReportType": "ProfitAndLoss", "ReportTitles": ["Profit and Loss", "Synthetic company", "For the month ended 31 January 2026"], "Rows": [
        {"RowType": "Header", "Cells": [{"Value": ""}, {"Value": "Jan 2026"}]},
        {"RowType": "Section", "Title": "Trading Income", "Rows": [
            {"RowType": "Row", "Cells": [{"Value": "Consulting", "Attributes": [{"Id": "account", "Value": "11111111-1111-4111-8111-111111111111"}]}, {"Value": "1000.10"}]},
            {"RowType": "SummaryRow", "Cells": [{"Value": "Total Trading Income"}, {"Value": "1000.10"}]}]},
        {"RowType": "Section", "Title": "Operating Expenses", "Rows": [
            {"RowType": "Row", "Cells": [{"Value": "Rent", "Attributes": [{"Id": "account", "Value": "22222222-2222-4222-8222-222222222222"}]}, {"Value": "300.05"}]},
            {"RowType": "SummaryRow", "Cells": [{"Value": "Total Operating Expenses"}, {"Value": "300.05"}]}]},
        {"RowType": "Section", "Title": "", "Rows": [
            {"RowType": "SummaryRow", "Cells": [{"Value": "Net Profit"}, {"Value": "700.05"}]}]}
    ]}]}


def report_client(tmp_path, body=None, status=200, enabled=True, organisation=None):
    """Return a signed-in application using only a scripted Xero transport."""
    calls = []
    async def handler(request):
        """Return organisation metadata or the supplied synthetic report."""
        calls.append(request)
        if request.url.path.endswith("/Organisation"):
            return httpx.Response(200, json={"Organisations": [organisation or {"BaseCurrency": "AUD", "Timezone": "UTC"}]})
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(status, json=body(request) if callable(body) else body if body is not None else report_body())
    settings = Settings(app_username="interviewer", app_password_hash=os.environ["APP_PASSWORD_HASH"],
                        session_secret="report-test", database_path=str(tmp_path / "reports.db"))
    settings = settings.model_copy(update={"performance_reports_enabled": enabled})
    app = create_app(settings=settings, invoices=FakeInvoiceGateway(), xero_http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    app.state.xero.connect(XeroConnection("synthetic-refresh", "synthetic-tenant", "Demo Company"), "synthetic-access", 1800)
    client = TestClient(app)
    sign_in(client)
    return client, calls

def test_profit_and_loss_requires_session(api) -> None:
    """Report amounts must never be returned to unsigned visitors."""
    client, _ = api
    response = client.get("/reports/profit-and-loss")
    assert response.status_code == 401
    assert response.json()["what"] == "Sign in required"


def test_profit_and_loss_returns_source_rows_without_private_ids(tmp_path) -> None:
    """A bounded standard P&L retains exact amounts, dates and evidence."""
    client, calls = report_client(tmp_path)
    with client:
        response = client.get("/reports/profit-and-loss", params={"date_from": "2026-01-01", "date_to": "2026-01-31"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schema_version"] == "1"
    assert body["currency"] == "AUD"
    assert body["basis"] == "accrual"
    assert body["date_from"] == "2026-01-01"
    assert body["date_to"] == "2026-01-31"
    assert body["rows"][0]["children"][0]["amount"] == "1000.10"
    assert body["rows"][-1]["children"][0]["amount"] == "700.05"
    assert "11111111-1111" not in response.text
    assert "Synthetic company" not in response.text
    assert body["retrieved_at"]
    assert [request.method for request in calls] == ["GET", "GET"]
    assert calls[-1].url.params["standardLayout"] == "true"
    assert calls[-1].url.params["paymentsOnly"] == "false"


def test_documented_xero_end_date_heading_and_profit_row(tmp_path) -> None:
    """Xero's documented date-column and un-IDed net-profit row stay supported."""
    body = report_body()
    report = body["Reports"][0]
    report["ReportTitles"][-1] = "1 January 2026 to 31 January 2026"
    report["Rows"][0]["Cells"][1]["Value"] = "31 Jan 26"
    report["Rows"][-1]["Rows"][0]["RowType"] = "Row"
    report["Rows"][-1]["Rows"][0]["Cells"][0]["Value"] = "NET PROFIT"
    client, _ = report_client(tmp_path, body)
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 200, response.text
    assert response.json()["rows"][-1]["children"][0]["kind"] == "summary"


def test_unknown_base_currency_is_not_presented_as_money(tmp_path) -> None:
    """An unsupported currency cannot silently use a guessed rounding precision."""
    client, calls = report_client(tmp_path, organisation={"BaseCurrency": "ZZZ", "Timezone": "UTC"})
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 422
    assert response.json()["what"] == "Report currency is unsupported"
    assert len(calls) == 1


def test_compressed_report_is_decoded_once_before_parsing(tmp_path) -> None:
    """The bounded transport must not decode an already decoded gzip body twice."""
    response = httpx.Response(200, stream=httpx.ByteStream(gzip.compress(json.dumps(report_body()).encode())), headers={"Content-Encoding": "gzip"})
    client, _ = report_client(tmp_path, response)
    with client:
        result = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert result.status_code == 200


@pytest.mark.parametrize("status", [401, 403])
def test_missing_report_consent_requires_reconnect(tmp_path, status) -> None:
    """Both Xero auth statuses produce actionable report-permission guidance."""
    client, _ = report_client(tmp_path, status=status)
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 403
    assert response.json()["what"] == "Report access required"
    assert "Reconnect Xero" in response.json()["next_step"]


def test_disabled_reports_do_not_read_xero(tmp_path) -> None:
    """The default-off rollout has an explicit state and does not call Xero."""
    client, calls = report_client(tmp_path, enabled=False)
    with client:
        response = client.get("/reports/profit-and-loss")
    assert response.status_code == 503
    assert response.json()["what"] == "Performance reports are disabled"
    assert calls == []


@pytest.mark.parametrize("body", [{"Reports": []}, {"Reports": [{"ReportType": "ProfitAndLoss", "Rows": []}]}])
def test_empty_report_has_no_inferred_profit(tmp_path, body) -> None:
    """An explicitly empty Xero report returns no invented totals."""
    client, _ = report_client(tmp_path, body)
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 200
    assert response.json()["status"] == "empty"
    assert response.json()["rows"] == []
    assert "profit" not in response.json()


@pytest.mark.parametrize("failure", ["missing_amount", "nonfinite", "wrong_header", "extra_column", "duplicate_identity", "wrong_type", "unknown_row"])
def test_malformed_report_is_not_a_plausible_zero(tmp_path, failure) -> None:
    """Malformed layouts, values and alignment fail without echoing source labels."""
    body = report_body()
    report = body["Reports"][0]
    account = report["Rows"][1]["Rows"][0]
    account["Cells"][0]["Value"] = "private@example.invalid"
    if failure == "missing_amount":
        del account["Cells"][1]["Value"]
    elif failure == "nonfinite":
        account["Cells"][1]["Value"] = "NaN"
    elif failure == "wrong_header":
        report["Rows"][0]["Cells"][1]["Value"] = "Feb 2026"
    elif failure == "extra_column":
        report["Rows"][0]["Cells"].append({"Value": "Dec 2025"})
    elif failure == "duplicate_identity":
        report["Rows"][2]["Rows"][0]["Cells"][0]["Attributes"] = account["Cells"][0]["Attributes"]
    elif failure == "wrong_type":
        report["ReportType"] = "BalanceSheet"
    else:
        account["RowType"] = "Chart"
    client, _ = report_client(tmp_path, body)
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 422
    assert "private@example.invalid" not in response.text
    assert "rows" not in response.json()


def test_report_leaf_cap_is_exact(tmp_path) -> None:
    """A 501st account fails rather than producing truncated financial figures."""
    body = report_body()
    section = body["Reports"][0]["Rows"][1]
    section["Rows"] = [{"RowType": "Row", "Cells": [{"Value": "Synthetic account", "Attributes": [{"Id": "account", "Value": str(UUID(int=index + 1))}]}, {"Value": "1.00"}]} for index in range(501)]
    client, _ = report_client(tmp_path, body)
    with client:
        response = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert response.status_code == 413
    assert "500" in response.json()["why"]


class TrackingStream(httpx.AsyncByteStream):
    """Track closure of a streamed synthetic response on success and failure."""

    def __init__(self, chunks):
        """Store bounded byte chunks and closure evidence."""
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        """Yield response chunks without a live network."""
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        """Record stream cleanup for assertions."""
        self.closed = True


@pytest.mark.parametrize("compressed", [False, True])
def test_oversize_response_is_capped_after_decompression(tmp_path, compressed) -> None:
    """The decoded-byte limit rejects compressed bombs and closes their streams."""
    payload = b'{"Reports":[],"padding":"' + b"x" * 1048576 + b'"}'
    data = gzip.compress(payload) if compressed else payload
    stream = TrackingStream([data[index:index + 4096] for index in range(0, len(data), 4096)])
    response = httpx.Response(200, stream=stream, headers={"Content-Encoding": "gzip"} if compressed else {})
    client, _ = report_client(tmp_path, response)
    with client:
        result = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert result.status_code == 413
    assert stream.closed is True
    assert "padding" not in result.text


def test_invalid_json_is_sanitized_and_closed(tmp_path) -> None:
    """Malformed provider content never leaks into the route's recovery message."""
    stream = TrackingStream([b"private report content, not JSON"])
    client, _ = report_client(tmp_path, httpx.Response(200, stream=stream))
    with client:
        result = client.get("/reports/profit-and-loss?date_from=2026-01-01&date_to=2026-01-31")
    assert result.status_code == 503
    assert stream.closed is True
    assert "private report content" not in result.text


def test_operation_deadline_cancels_report_read(tmp_path) -> None:
    """The whole-operation timeout cancels a blocked Xero request."""
    client, _ = report_client(tmp_path)
    cancelled = []
    async def slow_read(*args, **kwargs):
        """Block until the service's deadline cancels this read."""
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
    client.app.state.xero.get_bounded = slow_read
    client.app.state.services.reports._timeout_seconds = 0.01
    with client:
        result = client.get("/reports/profit-and-loss")
    assert result.status_code == 504
    assert cancelled == [True]


def test_default_period_uses_organisation_timezone(tmp_path, monkeypatch) -> None:
    """Month boundaries come from Xero's mapped timezone rather than UTC or browser time."""
    from app.reports import service
    class FixedDateTime(datetime):
        """Freeze an instant that is March in UTC but February in New York."""
        @classmethod
        def now(cls, tz=None):
            """Return one fixed instant expressed in the requested timezone."""
            return datetime(2026, 3, 1, 0, 30, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(service, "datetime", FixedDateTime)
    client, calls = report_client(tmp_path, organisation={"BaseCurrency": "USD", "Timezone": "EASTERNSTANDARDTIME"})
    with client:
        result = client.get("/reports/profit-and-loss")
    assert result.status_code == 200, result.text
    assert result.json()["date_from"] == "2026-01-01"
    assert result.json()["timezone"] == "America/New_York"
    assert calls[-1].url.params["toDate"] == "2026-01-31"


@pytest.mark.parametrize("zone", ["INVALIDZONE", "", None])
def test_unknown_timezone_never_defaults_to_utc(tmp_path, zone) -> None:
    """Missing or unsupported timezone metadata blocks inferred periods."""
    client, calls = report_client(tmp_path, organisation={"BaseCurrency": "AUD", "Timezone": zone})
    with client:
        result = client.get("/reports/profit-and-loss")
    assert result.status_code == 422
    assert len(calls) == 1


@pytest.mark.parametrize("dates", ["date_from=2026-02-01&date_to=2026-01-31", "date_from=2026-01-01", "date_from=2999-01-01&date_to=2999-01-31"])
def test_invalid_ranges_never_read_a_financial_report(tmp_path, dates) -> None:
    """Partial, reversed and future date ranges do not reach the report endpoint."""
    client, calls = report_client(tmp_path)
    with client:
        result = client.get(f"/reports/profit-and-loss?{dates}")
    assert result.status_code == 422
    assert all(not request.url.path.endswith("/ProfitAndLoss") for request in calls)
