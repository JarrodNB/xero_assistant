"""Purpose: Validate position accounting identities and compare trusted balance-sheet accounts.

Public API:
- compare_balance_sheets
- validate_balance_sheet
- resolve_position_dates
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from app.errors import ApiError
from app.reports.models import BalanceSheetComparison, BalanceSheetReport, PositionMovement, ReportRow
from app.reports.amounts import compare_amounts as _amounts
from app.reports.normalization import unsupported_report

CATEGORIES = {"assets": "assets", "bank": "assets", "current assets": "assets", "fixed assets": "assets",
              "non-current assets": "assets", "non current assets": "assets", "liabilities": "liabilities",
              "current liabilities": "liabilities", "non-current liabilities": "liabilities", "non current liabilities": "liabilities",
              "equity": "equity"}
GLOBAL_TOTALS = {"total assets": "assets", "total liabilities": "liabilities", "net assets": "net_assets",
                 "total equity": "equity", "total liabilities and equity": "liabilities_and_equity"}


@dataclass(frozen=True)
class _Position:
    """One trusted account and its financial section."""

    row: ReportRow
    category: str
    section: str


def resolve_position_dates(today: date, as_of: date | None, comparison_as_of: date | None,
                           preset: Literal["previous_month", "previous_year", "custom"]) -> tuple[date, date]:
    """Resolve point-in-time presets without inventing a P&L range."""
    if preset == "custom" and as_of is None:
        raise _invalid_dates()
    as_of = as_of or today.replace(day=1) - timedelta(days=1)
    if as_of.year < 1901 or as_of > today:
        raise _invalid_dates()
    if preset != "custom" and comparison_as_of is not None:
        raise _invalid_dates()
    if preset == "previous_month":
        previous_end = as_of.replace(day=1) - timedelta(days=1)
        comparison_as_of = previous_end if as_of.day == calendar.monthrange(as_of.year, as_of.month)[1] else previous_end.replace(day=min(as_of.day, previous_end.day))
    elif preset == "previous_year":
        comparison_as_of = as_of.replace(year=max(1, as_of.year - 1), day=min(as_of.day, calendar.monthrange(max(1, as_of.year - 1), as_of.month)[1]))
    if comparison_as_of is None or as_of == comparison_as_of or min(as_of.year, comparison_as_of.year) < 1901 or max(as_of, comparison_as_of) > today:
        raise _invalid_dates()
    return as_of, comparison_as_of


def _invalid_dates() -> ApiError:
    """Describe supported date choices without reflecting arbitrary input."""
    return ApiError(422, "Position dates are invalid", "Choose two distinct as-of dates on or before today in organisation time.", False,
                    "Use YYYY-MM-DD dates. Custom comparisons require both dates; presets do not accept a comparison date.")


def compare_balance_sheets(current: BalanceSheetReport, previous: BalanceSheetReport) -> BalanceSheetComparison:
    """Validate each accounting identity before aligning accounts and ranking position changes."""
    if (current.currency, current.currency_decimal_places, current.basis) != (previous.currency, previous.currency_decimal_places, previous.basis):
        raise unsupported_report()
    current, previous = current.model_copy(deep=True), previous.model_copy(deep=True)
    for prefix, report in (("current", current), ("comparison", previous)):
        for row in _walk(report.rows):
            row.key = f"{prefix}-{row.key}"
    warnings = ["The two reports are separate reads, not an atomic accounting snapshot.",
                "Balance-sheet changes describe positions at dates, not profit contributions or cash flows."]
    if current.status == "empty" or previous.status == "empty":
        validate_balance_sheet(current)
        validate_balance_sheet(previous)
        return BalanceSheetComparison(status="empty", current=current, comparison=previous, warnings=warnings + ["At least one date has no report data. No position changes were inferred."])
    with localcontext() as context:
        context.prec = 50
        tolerance = Decimal(1).scaleb(-current.currency_decimal_places)
        now_accounts, now_totals = _validate(current, tolerance)
        old_accounts, old_totals = _validate(previous, tolerance)
        metrics = {key: _amounts(now_totals[key], old_totals[key], current.currency_decimal_places) for key in ("assets", "liabilities", "equity", "net_assets")}
        movements = []
        for index, identity in enumerate(sorted(now_accounts.keys() | old_accounts.keys()), 1):
            now, old = now_accounts.get(identity), old_accounts.get(identity)
            selected = now or old
            assert selected is not None
            if now and old and now.category != old.category:
                raise unsupported_report()
            movements.append(PositionMovement(**_amounts(Decimal(now.row.amount) if now else Decimal(0), Decimal(old.row.amount) if old else Decimal(0), current.currency_decimal_places).model_dump(),
                key=f"position-{index}", label=selected.row.label, previous_label=old.row.label if now and old and now.row.label != old.row.label else None,
                category=selected.category, section=selected.section, current_source=now.row.key if now else None,
                comparison_source=old.row.key if old else None, account_id=identity))
        top = sorted((row for row in movements if Decimal(row.change)), key=lambda row: (-abs(Decimal(row.change)), row.key))[:5]
        return BalanceSheetComparison(status="ready", current=current, comparison=previous, metrics=metrics,
                                      movements=movements, top_movements=top, warnings=warnings)


def _walk(rows: list[ReportRow]):
    """Visit each original source row once."""
    for row in rows:
        yield row
        yield from _walk(row.children)


def _validate(report: BalanceSheetReport, tolerance: Decimal) -> tuple[dict[str, _Position], dict[str, Decimal]]:
    """Check supported sections, every subtotal and the full accounting identity."""
    accounts: dict[str, _Position] = {}
    reported: dict[str, Decimal] = {}

    def collect(row: ReportRow, inherited: str | None = None, section: str = "") -> Decimal:
        """Keep leaves distinct from financial summaries and validate their surrounding section."""
        label = row.label.casefold()
        if row.kind == "account":
            if inherited is None or row.account_id is None or row.account_id in accounts:
                raise unsupported_report()
            accounts[row.account_id] = _Position(row, inherited, section)
            return Decimal(row.amount)
        if row.kind == "summary":
            if label in GLOBAL_TOTALS:
                key = GLOBAL_TOTALS[label]
                if key in reported:
                    raise unsupported_report()
                reported[key] = Decimal(row.amount)
            elif inherited is None or not label.startswith("total "):
                raise unsupported_report()
            return Decimal(0)
        category = CATEGORIES.get(label, inherited)
        if inherited and category != inherited:
            raise unsupported_report()
        total = sum((collect(child, category, row.label or section) for child in row.children), Decimal(0))
        for child in row.children:
            if child.kind == "summary" and child.label.casefold().startswith("total "):
                global_key = GLOBAL_TOTALS.get(child.label.casefold())
                if global_key:
                    continue  # Overall totals reconcile against all classified accounts below.
                if child.label.casefold() != "total " + label or abs(Decimal(child.amount) - total) > tolerance:
                    raise unsupported_report()
        return total

    for row in report.rows:
        collect(row)
    totals = {category: sum((Decimal(value.row.amount) for value in accounts.values() if value.category == category), Decimal(0))
              for category in ("assets", "liabilities", "equity")}
    totals["net_assets"] = totals["assets"] - totals["liabilities"]
    if not {"assets", "liabilities", "equity", "net_assets"}.issubset(reported):
        raise unsupported_report()
    if any(abs(reported[key] - value) > tolerance for key, value in totals.items()) or abs(totals["net_assets"] - totals["equity"]) > tolerance:
        raise unsupported_report()
    if "liabilities_and_equity" in reported and abs(reported["liabilities_and_equity"] - totals["assets"]) > tolerance:
        raise unsupported_report()
    return accounts, totals


def validate_balance_sheet(report: BalanceSheetReport) -> None:
    """Validate each available position independently of the other comparison source."""
    if report.status == "empty":
        return
    with localcontext() as context:
        context.prec = 50
        _validate(report, Decimal(1).scaleb(-report.currency_decimal_places))
