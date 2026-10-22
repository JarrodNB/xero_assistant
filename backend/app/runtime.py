"""Purpose: Request-scoped services and conversation id for MCP tools.

Public API:
- AppServices
- current_services
- current_conversation_id
"""

from contextvars import ContextVar
from dataclasses import dataclass

from app.db.repository import ActionRepository
from app.invoices.gateway import InvoiceGateway
from app.reports.service import ReportService


@dataclass
class AppServices:
    """Dependencies a request hands to tools and routes."""

    invoices: InvoiceGateway
    actions: ActionRepository
    reports: ReportService | None = None


current_services: ContextVar[AppServices | None] = ContextVar("current_services", default=None)
current_conversation_id: ContextVar[str | None] = ContextVar("current_conversation_id", default=None)
