"""Purpose: Authenticated, read-only performance report endpoints.

Public API:
- router
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.auth.routes import require_user
from app.errors import ApiError
from app.reports.models import BalanceSheetComparison, BalanceSheetQuery, FinancialReport, ProfitAndLossQuery, ProfitComparisonQuery, ReportComparison
from app.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/profit-and-loss")
async def profit_and_loss(request: Request, query: Annotated[ProfitAndLossQuery, Query()]) -> FinancialReport:
    """Load a validated accrual P&L for the signed-in user."""
    require_user(request)
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled for this installation.", False, "Enable reporting after the demo access check.")
    service = ReportService(request.app.state.xero, settings.report_timeout_seconds)
    return await service.profit_and_loss(query.date_from, query.date_to)


@router.get("/profit-and-loss/comparison")
async def profit_and_loss_comparison(request: Request, query: Annotated[ProfitComparisonQuery, Query()]) -> ReportComparison:
    """Compare complete P&L ranges without invoking an AI model or accounting writes."""
    require_user(request)
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled for this installation.", False,
                       "Enable reporting after the demo access check.")
    return await ReportService(request.app.state.xero, settings.report_timeout_seconds).compare_profit_and_loss(
        query.date_from, query.date_to, query.comparison_from, query.comparison_to, query.preset)


@router.get("/balance-sheet/comparison")
async def balance_sheet_comparison(request: Request, query: Annotated[BalanceSheetQuery, Query()]) -> BalanceSheetComparison:
    """Compare complete financial positions without treating them as period activity."""
    require_user(request)
    settings = request.app.state.settings
    if not settings.performance_reports_enabled:
        raise ApiError(503, "Performance reports are disabled", "Reporting is not enabled for this installation.", False,
                       "Enable reporting after the demo access check.")
    return await ReportService(request.app.state.xero, settings.report_timeout_seconds).compare_balance_sheets(query.as_of, query.comparison_as_of, query.preset)
