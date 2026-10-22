"""Purpose: Resolve explicit P&L comparison ranges in organisation-local dates.

Public API:
- resolve_profit_periods
"""

import calendar
from datetime import date, timedelta
from typing import Literal

from app.errors import ApiError


def resolve_profit_periods(today: date, date_from: date | None, date_to: date | None,
                           comparison_from: date | None, comparison_to: date | None,
                           preset: Literal["previous_period", "previous_year", "custom"]) -> tuple[date, date, date, date]:
    """Default to completed months and resolve custom/preset dates without host timezone assumptions."""
    if date_from is None and date_to is None:
        date_to = today.replace(day=1) - timedelta(days=1)
        date_from = date_to.replace(day=1)
    _validate_range(date_from, date_to, today)
    if preset == "custom":
        _validate_range(comparison_from, comparison_to, today)
    elif comparison_from is not None or comparison_to is not None:
        raise _invalid_dates()
    elif preset == "previous_year":
        comparison_from, comparison_to = _previous_year(date_from), _previous_year(date_to)
    else:
        comparison_to = date_from - timedelta(days=1)
        full_month = date_from.day == 1 and date_to == date(date_from.year, date_from.month, calendar.monthrange(date_from.year, date_from.month)[1])
        comparison_from = comparison_to.replace(day=1) if full_month else comparison_to - (date_to - date_from)
    _validate_range(comparison_from, comparison_to, today)
    if (date_from, date_to) == (comparison_from, comparison_to):
        raise _invalid_dates()
    return date_from, date_to, comparison_from, comparison_to


def _validate_range(start: date | None, end: date | None, today: date) -> None:
    """Reject partial, reversed, future or minimum-bound ranges before report retrieval."""
    if start is None or end is None or start > end or end > today or start.year < 1901:
        raise _invalid_dates()


def _previous_year(value: date) -> date:
    """Preserve calendar dates while clamping leap day to the prior February end."""
    return value.replace(year=value.year - 1, day=min(value.day, calendar.monthrange(value.year - 1, value.month)[1]))


def _invalid_dates() -> ApiError:
    """Return date guidance without reflecting arbitrary query values."""
    return ApiError(422, "Comparison dates are invalid", "Choose two distinct complete date ranges on or before today in organisation time.",
                    False, "Use YYYY-MM-DD dates; custom comparisons require all four dates. Presets do not accept comparison dates.")
