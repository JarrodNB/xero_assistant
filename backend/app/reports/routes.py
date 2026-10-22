"""Purpose: Authenticated, read-only performance report endpoints.

Public API:
- router
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Request

from app.auth.routes import require_user
from app.errors import ApiError
from app.reports.models import FinancialReport, ReportComparison
from app.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/profit-and-loss")
async def profit_and_loss(request: Request, date_from: date | None = None, date_to: date | None = None) -> FinancialReport:
    """Load a validated accrual P&L for the signed-in user."""
    require_user(request)
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled for this installation.", False, "Enable reporting after the demo access check.")
    service = ReportService(request.app.state.xero, settings.report_timeout_seconds)
    return await service.profit_and_loss(date_from, date_to)


@router.get("/profit-and-loss/comparison")
async def profit_and_loss_comparison(request: Request, date_from: date | None = None, date_to: date | None = None,
                                    comparison_from: date | None = None, comparison_to: date | None = None,
                                    preset: Literal["previous_period", "previous_year", "custom"] = "previous_period") -> ReportComparison:
    """Compare complete P&L ranges without invoking an AI model or accounting writes."""
    require_user(request)
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled for this installation.", False,
                       "Enable reporting after the demo access check.")
    return await ReportService(request.app.state.xero, settings.report_timeout_seconds).compare_profit_and_loss(
        date_from, date_to, comparison_from, comparison_to, preset)
