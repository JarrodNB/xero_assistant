"""Purpose: Verify source-backed P&L comparisons through authenticated HTTP.

Public API:
- Offline report comparison regression cases
"""

from copy import deepcopy
from decimal import Decimal, localcontext
from datetime import date
from uuid import UUID

import pytest

from tests.test_reports import report_body, report_client
from app.reports.periods import resolve_profit_periods


def comparison_body(request):
    """Return two labelled synthetic periods with income up and profit down."""
    body = deepcopy(report_body())
    current = request.url.params["fromDate"] == "2026-02-01"
    rows = body["Reports"][0]["Rows"]
    if current:
        rows[0]["Cells"][1]["Value"] = "Feb 2026"
        for row in rows[1]["Rows"]:
            row["Cells"][1]["Value"] = "1500.10"
        for row in rows[2]["Rows"]:
            row["Cells"][1]["Value"] = "1000.05"
        rows[3]["Rows"][0]["Cells"][1]["Value"] = "500.05"
    return body


def test_compare_profit_and_loss_reconciles_signed_account_movements(tmp_path):
    """Reported expense increases explain a falling profit without double-counted totals."""
    client, calls = report_client(tmp_path, comparison_body)
    with client:
        response = client.get("/reports/profit-and-loss/comparison", params={
            "date_from": "2026-02-01", "date_to": "2026-02-28", "preset": "previous_period"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["metrics"]["net_profit"]["change"] == "-200.00"
    assert body["metrics"]["income"]["change"] == "500.00"
    assert body["metrics"]["expenses"]["change"] == "700.00"
    assert [item["contribution"] for item in body["top_movements"]] == ["-700.00", "500.00"]
    assert body["other_movements"] == "0.00"
    assert len(calls) == 3
    assert body["comparison"]["date_from"] == "2026-01-01"
    assert "11111111-1111" not in response.text


def test_unknown_summary_layout_is_rejected_even_when_profit_matches(tmp_path):
    """Unrecognized financial totals cannot appear beside a supposedly validated comparison."""
    def changed(request):
        """Insert a misleading unrecognized summary into an otherwise reconciled source."""
        body = comparison_body(request)
        body["Reports"][0]["Rows"][1]["Rows"].append({"RowType": "SummaryRow", "Cells": [{"Value": "Unrecognized result"}, {"Value": "900000.00"}]})
        return body
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == 422


def test_unbound_total_is_not_presented_as_validated_evidence(tmp_path):
    """A total outside a classified account section cannot silently escape reconciliation."""
    def changed(request):
        """Append a plausible but unsupported top-level financial total."""
        body = comparison_body(request)
        body["Reports"][0]["Rows"].append({"RowType": "SummaryRow", "Cells": [
            {"Value": "Total Income"}, {"Value": "999999.00"}]})
        return body
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == 422


def source_report(request, income, expenses, profit):
    """Build explicit-date synthetic sources from trusted account identities and exact values."""
    def section(title, accounts):
        """Create leaves and their exact subtotal without introducing incidental float math."""
        leaves = [{"RowType": "Row", "Cells": [{"Value": label, "Attributes": [{"Id": "account", "Value": str(UUID(int=identity))}]},
                    {"Value": amount}]} for identity, label, amount in accounts]
        with localcontext() as context:
            context.prec = 50
            total = sum((Decimal(amount) for _, _, amount in accounts), Decimal(0))
        return {"RowType": "Section", "Title": title, "Rows": leaves + [{"RowType": "SummaryRow", "Cells": [
            {"Value": "Total " + title}, {"Value": format(total, "f")}]}]}
    return {"Reports": [{"ReportType": "ProfitAndLoss", "Rows": [
        {"RowType": "Header", "Cells": [{"Value": ""}, {"Value": request.url.params["fromDate"] + " to " + request.url.params["toDate"]}]},
        section("Trading Income", income), section("Operating Expenses", expenses),
        {"RowType": "Section", "Title": "", "Rows": [{"RowType": "SummaryRow", "Cells": [{"Value": "Net Profit"}, {"Value": profit}]}]}]}]}


def test_ranked_contributors_and_remainder_reconcile_all_accounts(tmp_path):
    """Top-five evidence retains a remainder for the other changed accounts, without losing amounts."""
    def changed(request):
        """Return seven changing synthetic income accounts with identical labels."""
        current = request.url.params["fromDate"] == "2026-02-01"
        income = [(index, "Same label", str(index * 10 if current else index)) for index in range(1, 8)]
        return source_report(request, income, [], "280" if current else "28")
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["movements"]) == 7
    assert [row["contribution"] for row in result["top_movements"]] == ["63.00", "54.00", "45.00", "36.00", "27.00"]
    assert result["other_movements"] == "27.00"
    assert sum(Decimal(row["contribution"]) for row in result["top_movements"]) + Decimal(result["other_movements"]) == Decimal(result["metrics"]["net_profit"]["change"])
    assert all(row["current_source"].startswith("current-") and row["comparison_source"].startswith("comparison-") for row in result["movements"])


def test_renamed_new_and_credit_accounts_keep_their_financial_meaning(tmp_path):
    """Identities survive renames, new accounts start at zero, and negative expenses improve profit."""
    def changed(request):
        """Return renamed income, a new income account, and a negative expense credit."""
        current = request.url.params["fromDate"] == "2026-02-01"
        return source_report(request, [(1, "Renamed" if current else "Original", "100")] + ([(3, "New", "25")] if current else []),
                             [(2, "Expense", "-10" if current else "0")], "135" if current else "100")
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == 200, response.text
    result = response.json()
    rows = {row["label"]: row for row in result["movements"]}
    assert rows["Renamed"]["previous_label"] == "Original"
    assert rows["Renamed"]["change"] == "0.00"
    assert rows["New"]["comparison"] == "0.00" and rows["New"]["comparison_source"] is None
    assert rows["New"]["percentage_change"] is None
    assert rows["Expense"]["contribution"] == "10.00"
    assert result["metrics"]["net_profit"]["change"] == "35.00"


@pytest.mark.parametrize("failure", ["profit", "subtotal", "category", "empty"])
def test_unreconciled_or_missing_sources_never_become_zero_comparisons(tmp_path, failure):
    """Refuse invalid source math/meaning and explicitly distinguish no data from zero."""
    def changed(request):
        """Change only the comparison source into the selected failure mode."""
        body = comparison_body(request)
        if request.url.params["fromDate"] != "2026-01-01":
            return body
        rows = body["Reports"][0]["Rows"]
        if failure == "profit": rows[-1]["Rows"][0]["Cells"][1]["Value"] = "9999"
        elif failure == "subtotal": rows[1]["Rows"][-1]["Cells"][1]["Value"] = "9999"
        elif failure == "category": rows[1]["Title"] = "Unknown financial group"
        else: body["Reports"] = []
        return body
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == (200 if failure == "empty" else 422)
    if failure == "empty":
        assert response.json()["status"] == "empty"
        assert response.json()["metrics"] == {} and response.json()["movements"] == []


@pytest.mark.parametrize("preset,current,comparison,expected", [
    ("previous_period", (None, None), (None, None), (date(2026, 3, 1), date(2026, 3, 31), date(2026, 2, 1), date(2026, 2, 28))),
    ("previous_period", (date(2026, 3, 10), date(2026, 3, 19)), (None, None), (date(2026, 3, 10), date(2026, 3, 19), date(2026, 2, 28), date(2026, 3, 9))),
    ("previous_year", (date(2024, 2, 1), date(2024, 2, 29)), (None, None), (date(2024, 2, 1), date(2024, 2, 29), date(2023, 2, 1), date(2023, 2, 28))),
    ("custom", (date(2026, 3, 1), date(2026, 3, 31)), (date(2025, 11, 1), date(2025, 11, 15)), (date(2026, 3, 1), date(2026, 3, 31), date(2025, 11, 1), date(2025, 11, 15))),
])
def test_period_selection_preserves_calendar_and_custom_semantics(preset, current, comparison, expected):
    """Resolve calendar months, equal-day custom ranges and leap years explicitly."""
    assert resolve_profit_periods(date(2026, 4, 1), *current, *comparison, preset) == expected


def test_large_cancelling_accounts_retain_small_exact_movements(tmp_path):
    """Large positive/negative accounts do not erase small report changes through decimal rounding."""
    def changed(request):
        """Keep 200 account values at supported precision while their total remains small."""
        current = request.url.params["fromDate"] == "2026-02-01"
        income = [(index, "Large positive", "999999999999999999.12345678") for index in range(1, 101)]
        income += [(index, "Large negative", "-999999999999999999.12345677" if current else "-999999999999999999.12345678") for index in range(101, 201)]
        return source_report(request, income, [], "0.00000100" if current else "0.00000000")
    client, _ = report_client(tmp_path, changed)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?date_from=2026-02-01&date_to=2026-02-28")
    assert response.status_code == 200, response.text
    assert response.json()["metrics"]["net_profit"]["change"] == "0.00000100"


@pytest.mark.parametrize("dates", ["date_from=2026-02-28&date_to=2026-02-01", "date_from=2099-01-01&date_to=2099-01-31", "date_from=2026-02-01", "preset=custom", "comparison_from=2026-01-01&comparison_to=2026-01-31"])
def test_invalid_comparison_dates_do_not_request_reports(tmp_path, dates):
    """Invalid, partial, future or incompatible preset dates stop before financial reads."""
    client, calls = report_client(tmp_path, comparison_body)
    with client:
        response = client.get("/reports/profit-and-loss/comparison?" + dates)
    assert response.status_code == 422
    assert all(request.url.path.endswith("/Organisation") for request in calls)
