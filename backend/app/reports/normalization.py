"""Purpose: Validate bounded standard-layout Xero reports without guessing financial data.

Public API:
- normalize_profit_and_loss
- normalize_balance_sheet
- unsupported_report
"""

import calendar
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.errors import ApiError
from app.reports.models import ReportRow

MAX_LEAF_ROWS = 500
POSITION_TOTALS = {"total assets", "total liabilities", "net assets", "total equity", "total liabilities and equity"}


def unsupported_report() -> ApiError:
    """Return a sanitized error without reflecting untrusted report content."""
    return ApiError(422, "Report layout is unsupported", "The report could not be validated safely.", False,
                    "Use Xero's standard English accrual report, or inspect the report in Xero.")


def normalize_profit_and_loss(body: dict, date_from: date, date_to: date) -> list[ReportRow]:
    """Validate a single standard report and keep sections, amounts and evidence rows."""
    reports = body.get("Reports")
    if not isinstance(reports, list):
        raise unsupported_report()
    if not reports:
        return []
    if len(reports) != 1 or not isinstance(reports[0], dict):
        raise unsupported_report()
    report = reports[0]
    if report.get("ReportType") != "ProfitAndLoss":
        raise unsupported_report()
    rows = report.get("Rows")
    if not isinstance(rows, list):
        raise unsupported_report()
    if not rows:
        return []
    header = rows[0]
    if not isinstance(header, dict) or header.get("RowType") != "Header":
        raise unsupported_report()
    cells = _cells(header)
    if len(cells) != 2 or not _period_matches(cells[1].get("Value"), date_from, date_to, report.get("ReportTitles")):
        raise unsupported_report()
    state = {"leaves": 0, "rows": 0}
    seen: set[str] = set()
    return [_normalize_row(row, f"source-{index}", state, seen, 0) for index, row in enumerate(rows[1:], 1)]


def normalize_balance_sheet(body: dict, as_of: date) -> list[ReportRow]:
    """Require one explicitly dated position column before sharing bounded row extraction."""
    reports = body.get("Reports")
    if not isinstance(reports, list):
        raise unsupported_report()
    if not reports:
        return []
    if len(reports) != 1 or not isinstance(reports[0], dict) or reports[0].get("ReportType") != "BalanceSheet":
        raise unsupported_report()
    rows = reports[0].get("Rows")
    if not isinstance(rows, list):
        raise unsupported_report()
    if not rows:
        return []
    if not isinstance(rows[0], dict) or rows[0].get("RowType") != "Header":
        raise unsupported_report()
    cells = _cells(rows[0])
    if len(cells) != 2 or not isinstance(cells[1].get("Value"), str) or _heading_date(cells[1]["Value"]) != as_of:
        raise unsupported_report()
    state = {"leaves": 0, "rows": 0}
    seen: set[str] = set()
    return [_normalize_row(row, f"source-{index}", state, seen, 0, position=True) for index, row in enumerate(rows[1:], 1)]


def _period_matches(value: object, start: date, end: date, titles: object = None) -> bool:
    """Verify English month or explicit range headings against the requested dates."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    for pattern in ("%b %Y", "%B %Y"):
        try:
            month = datetime.strptime(text, pattern).date()
        except ValueError:
            continue
        return start == month and end == date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
    parts = re.split(r"\s+to\s+", text, flags=re.IGNORECASE)
    if len(parts) == 2:
        return _heading_date(parts[0]) == start and _heading_date(parts[1]) == end
    if _heading_date(text) == end and isinstance(titles, list):
        # A date-only column names its end, while the report title names the full range.
        return any(isinstance(title, str) and _period_matches(title, start, end) for title in titles)
    return False


def _heading_date(value: str) -> date | None:
    """Parse the documented English report-date forms without locale guessing."""
    for pattern in ("%d %b %Y", "%d %b %y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern).date()
        except ValueError:
            pass
    return None


def _cells(row: dict) -> list[dict]:
    """Require a well-formed row cell list before reading labels or numbers."""
    cells = row.get("Cells")
    if not isinstance(cells, list) or not all(isinstance(cell, dict) for cell in cells):
        raise unsupported_report()
    return cells


def _label(value: object, *, allow_empty: bool = False) -> str:
    """Bound untrusted source labels while preserving their visible meaning."""
    if not isinstance(value, str) or len(value) > 256 or (not value.strip() and not allow_empty):
        raise unsupported_report()
    return value.strip()


def _money(value: object) -> str:
    """Validate a finite exact decimal; missing cells never become zero."""
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,18}(?:\.\d{1,8})?", value):
        raise unsupported_report()
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise unsupported_report() from error
    if not amount.is_finite():
        raise unsupported_report()
    return format(amount, "f")


def _normalize_row(row: object, key: str, state: dict[str, int], seen: set[str], depth: int, *, position: bool = False) -> ReportRow:
    """Walk bounded sections without flattening or double-counting subtotal rows."""
    if not isinstance(row, dict) or depth > 10:
        raise unsupported_report()
    state["rows"] += 1
    if state["rows"] > 1500:
        raise unsupported_report()
    kind = row.get("RowType")
    if kind == "Section":
        label = _label(row.get("Title", ""), allow_empty=True)
        children = row.get("Rows")
        if not isinstance(children, list):
            raise unsupported_report()
        return ReportRow(key=key, kind="section", label=label,
                         children=[_normalize_row(child, f"{key}-{index}", state, seen, depth + 1, position=position)
                                   for index, child in enumerate(children, 1)])
    if kind not in {"Row", "SummaryRow"}:
        raise unsupported_report()
    cells = _cells(row)
    if len(cells) != 2:
        raise unsupported_report()
    label, amount = _label(cells[0].get("Value")), _money(cells[1].get("Value"))
    if kind == "SummaryRow":
        return ReportRow(key=key, kind="summary", label=label, amount=amount)
    identities = set()
    for cell in cells:
        attributes = cell.get("Attributes", [])
        if not isinstance(attributes, list) or not all(isinstance(item, dict) for item in attributes):
            raise unsupported_report()
        for item in attributes:
            if item.get("Id") == "account":
                try:
                    identities.add(str(UUID(item["Value"])))
                except (ValueError, TypeError, KeyError, AttributeError) as error:
                    raise unsupported_report() from error
    totals = POSITION_TOTALS if position else {"net profit", "net profit (loss)", "gross profit", "gross profit (loss)", "operating profit", "profit before tax", "profit after tax"}
    if not identities and label.casefold() in totals:
        return ReportRow(key=key, kind="summary", label=label, amount=amount)
    if len(identities) != 1:
        raise unsupported_report()
    state["leaves"] += 1
    if state["leaves"] > MAX_LEAF_ROWS:
        raise ApiError(413, "Report is too large", "The report exceeds 500 account rows.", False, "Choose a narrower date range or inspect the report in Xero.")
    identity = identities.pop()
    if identity in seen:
        raise unsupported_report()
    seen.add(identity)
    return ReportRow(key=key, kind="account", label=label, amount=amount, account_id=identity)
