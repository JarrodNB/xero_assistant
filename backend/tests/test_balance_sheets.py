"""Purpose: Verify source-backed balance-sheet positions through authenticated HTTP.

Public API:
- Offline balance-sheet regression cases
"""

from uuid import UUID
from copy import deepcopy
from datetime import date

import pytest

from tests.test_reports import report_client
from app.reports.balance_sheet import resolve_position_dates


def balance_body(request):
    """Return labelled synthetic accrual positions, never period activity."""
    current = request.url.params["date"] == "2026-02-28"

    def account(identity, label, amount):
        """Make a trusted account source with an exact decimal value."""
        return {"RowType": "Row", "Cells": [{"Value": label, "Attributes": [{"Id": "account", "Value": str(UUID(int=identity))}]}, {"Value": amount}]}

    def total(label, amount):
        """Make a reported summary, excluded from account movements."""
        return {"RowType": "SummaryRow", "Cells": [{"Value": label}, {"Value": amount}]}

    assets, liabilities, equity = ("1200", "400", "800") if current else ("1000", "300", "700")
    return {"Reports": [{"ReportType": "BalanceSheet", "ReportTitles": ["Balance Sheet", "Synthetic company", "As at " + request.url.params["date"]], "Rows": [
        {"RowType": "Header", "Cells": [{"Value": ""}, {"Value": request.url.params["date"]}]},
        {"RowType": "Section", "Title": "Assets", "Rows": [
            {"RowType": "Section", "Title": "Bank", "Rows": [account(1, "Bank", assets), total("Total Bank", assets)]}, total("Total Assets", assets)]},
        {"RowType": "Section", "Title": "Liabilities", "Rows": [account(2, "Accounts Payable", liabilities), total("Total Liabilities", liabilities)]},
        total("Net Assets", equity),
        {"RowType": "Section", "Title": "Equity", "Rows": [account(3, "Retained Earnings", equity), total("Total Equity", equity)]},
    ]}]}


def test_balance_sheet_compares_positions_without_profit_contributions(tmp_path):
    """Reported positions reconcile and retain their source rows without profit terminology."""
    client, calls = report_client(tmp_path, balance_body)
    with client:
        response = client.get("/reports/balance-sheet/comparison?as_of=2026-02-28&comparison_as_of=2026-01-31&preset=custom")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["report_type"] == "balance_sheet"
    assert result["current"]["as_of"] == "2026-02-28"
    assert result["metrics"]["assets"]["change"] == "200.00"
    assert result["metrics"]["liabilities"]["change"] == "100.00"
    assert result["metrics"]["equity"]["change"] == "100.00"
    assert {row["category"] for row in result["movements"]} == {"assets", "liabilities", "equity"}
    assert all("contribution" not in row for row in result["movements"])
    assert "net_profit" not in result["metrics"]
    assert str(UUID(int=1)) not in response.text
    assert len(calls) == 3
    assert all(request.url.params["periods"] == "0" for request in calls[1:])


def test_flat_sections_and_unidentified_total_rows_reconcile(tmp_path):
    """Xero's flat financial section layout retains negative asset accounts and global totals."""
    def flat(request):
        """Flatten the category hierarchy and keep overall totals in blank sections."""
        body = balance_body(request)
        rows = body["Reports"][0]["Rows"]
        bank = rows[1]["Rows"][0]
        negative = deepcopy(bank["Rows"][0])
        negative["Cells"][0] = {"Value": "Accumulated Depreciation", "Attributes": [{"Id": "account", "Value": str(UUID(int=4))}]}
        negative["Cells"][1]["Value"] = "-100"
        # Increase the bank balance by the contra account, preserving reported total assets.
        bank["Rows"][0]["Cells"][1]["Value"] = "1300" if request.url.params["date"] == "2026-02-28" else "1100"
        bank["Rows"][-1]["Cells"][1]["Value"] = bank["Rows"][0]["Cells"][1]["Value"]
        total_assets = rows[1]["Rows"][-1]
        total_assets["RowType"] = "Row"
        body["Reports"][0]["Rows"] = [rows[0], {"RowType": "Section", "Title": "Assets", "Rows": []}, bank,
            {"RowType": "Section", "Title": "Fixed Assets", "Rows": [negative, {"RowType": "SummaryRow", "Cells": [{"Value": "Total Fixed Assets"}, {"Value": "-100"}]}]},
            {"RowType": "Section", "Title": "", "Rows": [total_assets]}, *rows[2:]]
        return body
    client, _ = report_client(tmp_path, flat)
    with client:
        response = client.get("/reports/balance-sheet/comparison?as_of=2026-02-28")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metrics"]["assets"]["current"] == "1200.00"
    assert next(row for row in result["movements"] if row["label"] == "Accumulated Depreciation")["current"] == "-100.00"
    assert result["comparison"]["as_of"] == "2026-01-31"


@pytest.mark.parametrize("failure", ["identity", "subtotal", "missing_total", "unknown_section", "duplicate_id", "date", "extra_column", "unknown_total"])
def test_invalid_position_sources_are_rejected(tmp_path, failure):
    """Ambiguous source structure and failed accounting identities never produce plausible positions."""
    def changed(request):
        """Corrupt one source invariant without changing the response envelope."""
        body = balance_body(request)
        rows = body["Reports"][0]["Rows"]
        if failure == "identity":
            rows[-1]["Rows"][0]["Cells"][1]["Value"] = "9999"
            rows[-1]["Rows"][1]["Cells"][1]["Value"] = "9999"
        elif failure == "subtotal": rows[1]["Rows"][0]["Rows"][-1]["Cells"][1]["Value"] = "9999"
        elif failure == "missing_total": rows.pop(3)
        elif failure == "unknown_section": rows[1]["Title"] = "Unverified position group"; rows[1]["Rows"][0]["Title"] = "Unknown"
        elif failure == "duplicate_id": rows[2]["Rows"][0]["Cells"][0]["Attributes"][0]["Value"] = str(UUID(int=1))
        elif failure == "date": rows[0]["Cells"][1]["Value"] = "2020-01-01"
        elif failure == "extra_column": rows[0]["Cells"].append({"Value": "2020-01-01"})
        else: rows[1]["Rows"][0]["Rows"][-1]["Cells"][0]["Value"] = "Total unrelated figure"
        return body
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/balance-sheet/comparison?as_of=2026-02-28")
    assert response.status_code == 422, response.text


def test_empty_position_source_is_not_zero(tmp_path):
    """An empty comparative source preserves honest absence instead of fabricated changes."""
    def empty(request):
        """Return no report for one of the requested dates."""
        return {"Reports": []} if request.url.params["date"] == "2026-01-31" else balance_body(request)
    client, _ = report_client(tmp_path, empty)
    with client:
        response = client.get("/reports/balance-sheet/comparison?as_of=2026-02-28")
    assert response.status_code == 200
    assert response.json()["status"] == "empty"
    assert response.json()["metrics"] == {} and response.json()["movements"] == []


@pytest.mark.parametrize("current,previous,preset,expected", [
    (None, None, "previous_month", (date(2026, 3, 31), date(2026, 2, 28))),
    (date(2026, 3, 15), None, "previous_month", (date(2026, 3, 15), date(2026, 2, 15))),
    (date(2024, 2, 29), None, "previous_year", (date(2024, 2, 29), date(2023, 2, 28))),
    (date(2026, 3, 31), date(2025, 6, 30), "custom", (date(2026, 3, 31), date(2025, 6, 30))),
])
def test_position_presets_keep_as_of_semantics(current, previous, preset, expected):
    """Month-end and leap dates resolve deliberately rather than becoming period ranges."""
    assert resolve_position_dates(date(2026, 4, 1), current, previous, preset) == expected


@pytest.mark.parametrize("query", ["as_of=2099-01-01", "preset=custom", "preset=custom&as_of=2026-02-28", "preset=custom&as_of=2026-02-28&comparison_as_of=2026-02-28", "as_of=0001-01-01", "comparison_as_of=2026-01-31", "date_from=2026-01-01"])
def test_invalid_position_dates_do_not_read_financial_data(tmp_path, query):
    """Partial, future, duplicate, out-of-range and incompatible queries stop before reports."""
    client, calls = report_client(tmp_path, balance_body)
    with client:
        response = client.get("/reports/balance-sheet/comparison?" + query)
    assert response.status_code == 422, response.text
    assert all(request.url.path.endswith("/Organisation") for request in calls)


def test_position_account_reclassification_is_not_a_silent_match(tmp_path):
    """A trusted id moving between financial categories cannot be compared as the same kind of position."""
    def reclassified(request):
        """Swap private identities while keeping both report totals valid."""
        body = balance_body(request)
        if request.url.params["date"] == "2026-02-28":
            body["Reports"][0]["Rows"][1]["Rows"][0]["Rows"][0]["Cells"][0]["Attributes"][0]["Value"] = str(UUID(int=2))
            body["Reports"][0]["Rows"][2]["Rows"][0]["Cells"][0]["Attributes"][0]["Value"] = str(UUID(int=1))
        return body
    client, _ = report_client(tmp_path, reclassified)
    with client:
        assert client.get("/reports/balance-sheet/comparison?as_of=2026-02-28").status_code == 422


def test_new_position_account_has_verified_zero_baseline(tmp_path):
    """A missing account becomes zero only after both source identities reconcile."""
    def new_account(request):
        """Split one current asset into two accounts without changing financial totals."""
        body = balance_body(request)
        if request.url.params["date"] == "2026-02-28":
            rows = body["Reports"][0]["Rows"][1]["Rows"][0]["Rows"]
            rows[0]["Cells"][1]["Value"] = "1100"
            extra = deepcopy(rows[0])
            extra["Cells"][0] = {"Value": "New account", "Attributes": [{"Id": "account", "Value": str(UUID(int=4))}]}
            extra["Cells"][1]["Value"] = "100"
            rows.insert(1, extra)
        return body
    client, _ = report_client(tmp_path, new_account)
    with client:
        response = client.get("/reports/balance-sheet/comparison?as_of=2026-02-28")
    assert response.status_code == 200, response.text
    row = next(row for row in response.json()["movements"] if row["label"] == "New account")
    assert row["comparison"] == "0.00" and row["comparison_source"] is None
    assert row["percentage_change"] is None and row["percentage_note"]


def test_balance_sheet_is_authenticated_and_flagged(api, tmp_path):
    """The new read interface keeps the session and rollout controls of existing reports."""
    client, _ = api
    assert client.get("/reports/balance-sheet/comparison").status_code == 401
    disabled, calls = report_client(tmp_path, balance_body, enabled=False)
    with disabled:
        assert disabled.get("/reports/balance-sheet/comparison").status_code == 503
    assert calls == []
