"""Purpose: Compare exact report amounts without losing precision or inventing percentages.

Public API:
- compare_amounts
- fixed_amount
"""

from decimal import Decimal

from app.reports.models import AmountComparison


def fixed_amount(value: Decimal, precision: int) -> str:
    """Pad to the currency minimum without dropping reported precision."""
    return format(value, f".{max(precision, -value.as_tuple().exponent)}f")


def compare_amounts(current: Decimal, previous: Decimal, precision: int) -> AmountComparison:
    """Use exact figures and omit misleading nonpositive-baseline percentages."""
    change = current - previous
    return AmountComparison(current=fixed_amount(current, precision), comparison=fixed_amount(previous, precision), change=fixed_amount(change, precision),
        percentage_change=format((change / previous * 100).quantize(Decimal("0.01")), "f") if previous > 0 else None,
        percentage_note=None if previous > 0 else "Percentage change is unavailable because the comparison amount is zero or negative.")
