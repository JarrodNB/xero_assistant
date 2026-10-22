"""Purpose: Read complete, bounded accrual reports with trusted organisation metadata.

Public API:
- ReportService
"""

import asyncio
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Literal

from app.errors import ApiError
from app.reports.models import BalanceSheetComparison, BalanceSheetReport, FinancialReport, ReportComparison
from app.reports.balance_sheet import compare_balance_sheets, resolve_position_dates
from app.reports.comparison import compare_profit_and_loss
from app.reports.normalization import normalize_balance_sheet, normalize_profit_and_loss, unsupported_report
from app.reports.periods import resolve_profit_periods
from app.xero.client import XeroApiError, XeroClient

# Xero returns Windows timezone names, not necessarily IANA identifiers.
ORGANISATION_ZONES = {
    "UTC": "UTC", "GMTSTANDARDTIME": "Europe/London", "NEWZEALANDSTANDARDTIME": "Pacific/Auckland",
    "AUSEASTERNSTANDARDTIME": "Australia/Sydney", "E. AUSTRALIASTANDARDTIME": "Australia/Brisbane",
    "EAUSTRALIASTANDARDTIME": "Australia/Brisbane", "W. AUSTRALIASTANDARDTIME": "Australia/Perth",
    "WAUSTRALIASTANDARDTIME": "Australia/Perth", "CEN. AUSTRALIASTANDARDTIME": "Australia/Adelaide",
    "CENAUSTRALIASTANDARDTIME": "Australia/Adelaide", "EASTERNSTANDARDTIME": "America/New_York",
    "CENTRALSTANDARDTIME": "America/Chicago", "MOUNTAINSTANDARDTIME": "America/Denver",
    "PACIFICSTANDARDTIME": "America/Los_Angeles", "SINGAPORESTANDARDTIME": "Asia/Singapore",
}

# Explicitly supported base currencies; unknown codes must not inherit a guessed precision.
CURRENCY_DECIMAL_PLACES = {
    "AUD": 2, "NZD": 2, "USD": 2, "CAD": 2, "GBP": 2, "EUR": 2,
    "SGD": 2, "HKD": 2, "ZAR": 2, "INR": 2, "PHP": 2, "CNY": 2,
    "JPY": 0, "KRW": 0, "BHD": 3, "KWD": 3, "OMR": 3,
}


class ReportService:
    """Own report retrieval, validation and time/currency context behind one interface."""

    def __init__(self, client: XeroClient, timeout_seconds: float = 30) -> None:
        """Keep the existing client and the whole-operation cancellation budget."""
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def profit_and_loss(self, date_from: date | None = None, date_to: date | None = None) -> FinancialReport:
        """Return one explicitly dated accrual P&L, defaulting in organisation time."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                currency, zone = await self._organisation()
                today = datetime.now(ZoneInfo(zone)).date()
                if date_from is None and date_to is None:
                    date_to = today.replace(day=1) - timedelta(days=1)
                    date_from = date_to.replace(day=1)
                if date_from is None or date_to is None or date_from > date_to or date_to > today:
                    raise ApiError(422, "Report dates are invalid", "Choose a start and end date on or before today in the organisation timezone.",
                                   False, "Use YYYY-MM-DD dates with the start on or before the end.")
                body = await self._client.get_bounded("/Reports/ProfitAndLoss", {"fromDate": date_from.isoformat(), "toDate": date_to.isoformat(),
                                                                               "standardLayout": "true", "paymentsOnly": "false"})
                rows = normalize_profit_and_loss(body, date_from, date_to)
                return FinancialReport(status="ready" if rows else "empty", date_from=date_from, date_to=date_to,
                                       currency=currency, currency_decimal_places=CURRENCY_DECIMAL_PLACES[currency],
                                       timezone=zone, retrieved_at=datetime.now(timezone.utc), rows=rows)
        except TimeoutError as error:
            raise ApiError(504, "Report request timed out", "Xero did not return a complete report within the operation deadline.",
                           True, "Try again later. No partial figures were used.") from error
        except XeroApiError as error:
            if error.status_code in {401, 403, 409}:
                raise ApiError(403, "Report access required", "The Xero connection or user does not have report access.",
                               False, "Reconnect Xero and grant report permissions using an account allowed to view reports.") from error
            if error.status_code == 413:
                raise ApiError(413, "Report is too large", "Xero's response exceeds the report byte limit.",
                               False, "Choose a narrower date range or inspect the report in Xero.") from error
            raise ApiError(503, "Report is unavailable", "Xero did not return a usable report.", True,
                           "Try again later or inspect the report in Xero. No figures were inferred.") from error

    async def _organisation(self) -> tuple[str, str]:
        """Validate base currency and map explicitly supported organisation timezones."""
        body = await self._client.get_bounded("/Organisation")
        organisations = body.get("Organisations")
        if not isinstance(organisations, list) or len(organisations) != 1 or not isinstance(organisations[0], dict):
            raise unsupported_report()
        organisation = organisations[0]
        currency = organisation.get("BaseCurrency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise unsupported_report()
        if currency not in CURRENCY_DECIMAL_PLACES:
            raise ApiError(422, "Report currency is unsupported", "The base currency has no verified precision policy.",
                           False, "Inspect reports in Xero until this currency is supported.")
        raw_zone = organisation.get("Timezone")
        if not isinstance(raw_zone, str):
            raise unsupported_report()
        zone = ORGANISATION_ZONES.get(raw_zone.replace(" ", "").upper())
        if zone is None:
            raise ApiError(422, "Organisation timezone is unsupported", "The organisation timezone has no verified mapping.",
                           False, "Inspect reports in Xero until this timezone is supported.")
        try:
            ZoneInfo(zone)
        except ZoneInfoNotFoundError as error:
            raise unsupported_report() from error
        return currency, zone

    async def compare_profit_and_loss(self, date_from: date | None = None, date_to: date | None = None,
                                     comparison_from: date | None = None, comparison_to: date | None = None,
                                     preset: Literal["previous_period", "previous_year", "custom"] = "previous_period") -> ReportComparison:
        """Read two P&Ls and reconcile their movements under one operation deadline."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                currency, zone = await self._organisation()
                dates = resolve_profit_periods(datetime.now(ZoneInfo(zone)).date(), date_from, date_to,
                                               comparison_from, comparison_to, preset)
                current = await self._profit_report(dates[0], dates[1], currency, zone)
                previous = await self._profit_report(dates[2], dates[3], currency, zone)
                return compare_profit_and_loss(current, previous)
        except TimeoutError as error:
            raise ApiError(504, "Report request timed out", "Xero did not return both complete reports within the operation deadline.",
                           True, "Try again later. No partial comparison was used.") from error
        except XeroApiError as error:
            if error.status_code in {401, 403, 409}:
                raise ApiError(403, "Report access required", "The Xero connection or user does not have report access.",
                               False, "Reconnect Xero and grant report permissions using an account allowed to view reports.") from error
            if error.status_code == 413:
                raise ApiError(413, "Report is too large", "Xero's response exceeds the report byte limit.", False,
                               "Choose a narrower date range or inspect the report in Xero.") from error
            raise ApiError(503, "Report is unavailable", "Xero did not return a usable comparison.", True,
                           "Try again later or inspect the reports in Xero. No figures were inferred.") from error

    async def _profit_report(self, start: date, end: date, currency: str, zone: str) -> FinancialReport:
        """Fetch one validated range using metadata already read for this operation."""
        body = await self._client.get_bounded("/Reports/ProfitAndLoss", {"fromDate": start.isoformat(), "toDate": end.isoformat(),
                                                                       "standardLayout": "true", "paymentsOnly": "false"})
        rows = normalize_profit_and_loss(body, start, end)
        return FinancialReport(status="ready" if rows else "empty", date_from=start, date_to=end,
                               currency=currency, currency_decimal_places=CURRENCY_DECIMAL_PLACES[currency],
                               timezone=zone, retrieved_at=datetime.now(timezone.utc), rows=rows)

    async def compare_balance_sheets(self, as_of: date | None = None, comparison_as_of: date | None = None,
                                     preset: Literal["previous_month", "previous_year", "custom"] = "previous_month") -> BalanceSheetComparison:
        """Read two explicitly dated positions under the existing bounded operation budget."""
        try:
            async with asyncio.timeout(self._timeout_seconds):
                currency, zone = await self._organisation()
                dates = resolve_position_dates(datetime.now(ZoneInfo(zone)).date(), as_of, comparison_as_of, preset)
                current = await self._position_report(dates[0], currency, zone)
                previous = await self._position_report(dates[1], currency, zone)
                return compare_balance_sheets(current, previous)
        except TimeoutError as error:
            raise ApiError(504, "Report request timed out", "Xero did not return both complete reports within the operation deadline.", True,
                           "Try again later. No partial comparison was used.") from error
        except XeroApiError as error:
            if error.status_code in {401, 403, 409}:
                raise ApiError(403, "Report access required", "The Xero connection or user does not have report access.", False,
                               "Reconnect Xero and grant report permissions using an account allowed to view reports.") from error
            if error.status_code == 413:
                raise ApiError(413, "Report is too large", "Xero's response exceeds the report byte limit.", False,
                               "Inspect the report in Xero.") from error
            raise ApiError(503, "Report is unavailable", "Xero did not return a usable comparison.", True,
                           "Try again later or inspect the reports in Xero. No figures were inferred.") from error

    async def _position_report(self, as_of: date, currency: str, zone: str) -> BalanceSheetReport:
        """Ask for exactly one position column and verify its returned date."""
        body = await self._client.get_bounded("/Reports/BalanceSheet", {"date": as_of.isoformat(), "periods": 0,
                                                                      "standardLayout": "true", "paymentsOnly": "false"})
        rows = normalize_balance_sheet(body, as_of)
        return BalanceSheetReport(status="ready" if rows else "empty", as_of=as_of, currency=currency,
                                  currency_decimal_places=CURRENCY_DECIMAL_PLACES[currency], timezone=zone,
                                  retrieved_at=datetime.now(timezone.utc), rows=rows)
