"""Purpose: Reconcile standard P&L sources and calculate exact account movements.

Public API:
- compare_profit_and_loss
"""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.reports.models import AccountMovement, AmountComparison, FinancialReport, ReportComparison, ReportRow
from app.reports.normalization import unsupported_report

INCOME_SECTIONS = {"trading income", "income", "revenue", "other income", "non-operating income"}
EXPENSE_SECTIONS = {"cost of sales", "less cost of sales", "direct costs", "operating expenses", "expenses",
                    "other expenses", "non-operating expenses", "tax", "taxation", "income tax", "tax expense"}
PROFIT_LABELS = {"net profit", "net profit (loss)", "net profit / (loss)"}
GROSS_LABELS = {"gross profit", "gross profit (loss)"}


@dataclass(frozen=True)
class _Account:
    """One trusted leaf with its report semantics and source key."""

    row: ReportRow
    category: str
    gross: bool


def compare_profit_and_loss(current: FinancialReport, previous: FinancialReport) -> ReportComparison:
    """Align complete source reports and reconcile their signed profit contributors."""
    if (current.currency, current.currency_decimal_places, current.basis) != (previous.currency, previous.currency_decimal_places, previous.basis):
        raise unsupported_report()
    current, previous = _prefix_sources(current, "current"), _prefix_sources(previous, "comparison")
    warnings = ["The two reports are separate reads, not an atomic accounting snapshot."]
    if (current.date_to - current.date_from).days != (previous.date_to - previous.date_from).days:
        warnings.append("The selected P&L periods have unequal lengths; interpret changes with care.")
    if current.status == "empty" or previous.status == "empty":
        return ReportComparison(status="empty", current=current, comparison=previous, warnings=warnings + [
            "At least one period has no report data. No totals or account changes have been inferred."])
    with localcontext() as context:
        context.prec = 50
        precision = current.currency_decimal_places
        tolerance = Decimal(1).scaleb(-precision)
        now_accounts, now_metrics = _validate_report(current, tolerance)
        old_accounts, old_metrics = _validate_report(previous, tolerance)
        metrics = {name: _amounts(now_metrics[name], old_metrics[name], precision) for name in now_metrics}
        movements = []
        for index, identity in enumerate(sorted(now_accounts.keys() | old_accounts.keys()), 1):
            now, old = now_accounts.get(identity), old_accounts.get(identity)
            chosen = now or old
            assert chosen is not None
            if now and old and now.category != old.category:
                raise unsupported_report()
            amount = _amounts(Decimal(now.row.amount) if now else Decimal(0), Decimal(old.row.amount) if old else Decimal(0), precision)
            contribution = Decimal(amount.change) * (1 if chosen.category == "income" else -1)
            movements.append(AccountMovement(**amount.model_dump(), key=f"movement-{index}", label=chosen.row.label,
                previous_label=old.row.label if now and old and now.row.label != old.row.label else None,
                category=chosen.category, contribution=_fixed(contribution, precision), account_id=identity,
                current_source=now.row.key if now else None, comparison_source=old.row.key if old else None))
        if abs(sum((Decimal(item.contribution) for item in movements), Decimal(0)) - Decimal(metrics["net_profit"].change)) > tolerance:
            raise unsupported_report()
        ranked = sorted((item for item in movements if Decimal(item.contribution) != 0),
                        key=lambda item: (-abs(Decimal(item.contribution)), item.key))
        top = ranked[:5]
        remainder = Decimal(metrics["net_profit"].change) - sum((Decimal(item.contribution) for item in top), Decimal(0))
        return ReportComparison(status="ready", current=current, comparison=previous, metrics=metrics, movements=movements,
                                top_movements=top, other_movements=_fixed(remainder, precision), warnings=warnings)


def _prefix_sources(report: FinancialReport, prefix: str) -> FinancialReport:
    """Keep both original report trees addressable without duplicate public row keys."""
    copied = report.model_copy(deep=True)
    for row in _walk(copied.rows):
        row.key = f"{prefix}-{row.key}"
    return copied


def _walk(rows: list[ReportRow]):
    """Yield each row exactly once, including nested sections and totals."""
    for row in rows:
        yield row
        yield from _walk(row.children)


def _validate_report(report: FinancialReport, tolerance: Decimal) -> tuple[dict[str, _Account], dict[str, Decimal]]:
    """Establish section meanings, subtotal consistency and profit reconciliation."""
    accounts: dict[str, _Account] = {}
    profits = [row for row in _walk(report.rows) if row.kind == "summary" and row.label.casefold() in PROFIT_LABELS]
    if len(profits) != 1:
        raise unsupported_report()
    for row in report.rows:
        _collect_accounts(row, None, accounts, tolerance)
    income = sum((Decimal(item.row.amount) for item in accounts.values() if item.category == "income"), Decimal(0))
    expenses = sum((Decimal(item.row.amount) for item in accounts.values() if item.category == "expenses"), Decimal(0))
    profit = Decimal(profits[0].amount)
    if abs(income - expenses - profit) > tolerance:
        raise unsupported_report()
    gross_rows = [row for row in _walk(report.rows) if row.kind == "summary" and row.label.casefold() in GROSS_LABELS]
    gross = sum((Decimal(item.row.amount) * (1 if item.category == "income" else -1)
                 for item in accounts.values() if item.gross), Decimal(0))
    if len(gross_rows) > 1 or any(abs(Decimal(row.amount) - gross) > tolerance for row in gross_rows):
        raise unsupported_report()
    return accounts, {"income": income, "expenses": expenses, "net_profit": profit}


def _collect_accounts(row: ReportRow, inherited: str | None, accounts: dict[str, _Account], tolerance: Decimal, gross: bool = False) -> Decimal:
    """Collect leaves only; subtotal rows validate but never become contributors."""
    if row.kind == "account":
        if inherited is None or row.account_id is None or row.account_id in accounts:
            raise unsupported_report()
        accounts[row.account_id] = _Account(row, inherited, gross)
        return Decimal(row.amount)
    if row.kind == "summary":
        if row.label.casefold().startswith("total ") and inherited is None:
            raise unsupported_report()
        if not row.label.casefold().startswith("total ") and row.label.casefold() not in PROFIT_LABELS | GROSS_LABELS:
            raise unsupported_report()
        return Decimal(0)
    label = row.label.casefold()
    category = "income" if label in INCOME_SECTIONS else "expenses" if label in EXPENSE_SECTIONS else inherited
    if inherited and category != inherited:
        raise unsupported_report()
    if label in INCOME_SECTIONS | EXPENSE_SECTIONS:
        gross = label in {"trading income", "income", "revenue", "cost of sales", "less cost of sales", "direct costs"}
    total = sum((_collect_accounts(child, category, accounts, tolerance, gross) for child in row.children), Decimal(0))
    subtotals = [child for child in row.children if child.kind == "summary" and child.label.casefold().startswith("total ")]
    if any(abs(Decimal(child.amount) - total) > tolerance for child in subtotals):
        raise unsupported_report()
    return total


def _amounts(current: Decimal, previous: Decimal, precision: int) -> AmountComparison:
    """Use exact decimal amounts and omit misleading nonpositive-baseline percentages."""
    change = current - previous
    return AmountComparison(current=_fixed(current, precision), comparison=_fixed(previous, precision), change=_fixed(change, precision),
        percentage_change=format((change / previous * 100).quantize(Decimal("0.01")), "f") if previous > 0 else None,
        percentage_note=None if previous > 0 else "Percentage change is unavailable because the comparison amount is zero or negative.")


def _fixed(value: Decimal, precision: int) -> str:
    """Retain all reported precision while padding to the verified currency minimum."""
    places = max(precision, -value.as_tuple().exponent)
    return format(value, f".{places}f")
