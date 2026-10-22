"""Purpose: Bind expiring report selections to private account identity without retaining snapshots.

Public API:
- ReportContexts
- ReportSelection
- invalid_context
"""

import hashlib
import hmac
import json
import secrets
from datetime import date
from typing import Literal

from itsdangerous import BadData, URLSafeTimedSerializer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.errors import ApiError
from app.reports.models import BalanceSheetComparison, ReportComparison
from app.reports.service import ReportService
from app.xero.connection_store import XeroConnectionStore


class ReportSelection(BaseModel):
    """Only public dates and an opaque binding travel through the browser."""

    model_config = ConfigDict(extra="forbid")
    report_type: Literal["profit_and_loss", "balance_sheet"]
    dates: list[date] = Field(min_length=2, max_length=4)
    nonce: str = Field(min_length=16, max_length=64)
    tenant_binding: str = Field(pattern=r"^[a-f0-9]{64}$")
    account_binding: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


def invalid_context() -> ApiError:
    """Reject invalid context without revealing its signed payload or underlying account."""
    return ApiError(409, "Report selection needs refreshing", "The report selection expired, changed, or is unavailable.",
                    False, "Reopen Performance, choose the account again, and submit a new question.")


class ReportContexts:
    """Sign selections and resolve them only against fresh trusted report reads."""

    def __init__(self, secret: str, connections: XeroConnectionStore, max_age: int = 900, result_byte_limit: int = 2097152) -> None:
        """Keep the signing key and trusted tenant lookup, never report snapshots."""
        self._secret = secret.encode()
        self._serializer = URLSafeTimedSerializer(secret, salt="ledger-report-context-v1")
        self._connections = connections
        self._max_age = max_age
        self._result_byte_limit = result_byte_limit

    def _digest(self, *values: str) -> str:
        """Create a domain-separated opaque identity binding with canonical framing."""
        return hmac.new(self._secret, json.dumps(values, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()

    def _tenant(self) -> str:
        """Resolve the connected tenant inside the trusted application."""
        connection = self._connections.load()
        if connection is None:
            raise invalid_context()
        return connection.tenant_id

    def decorate(self, report: ReportComparison | BalanceSheetComparison):
        """Issue overview and account selectors without disclosing private IDs."""
        dates = ([report.current.date_from, report.current.date_to, report.comparison.date_from, report.comparison.date_to]
                 if isinstance(report, ReportComparison) else [report.current.as_of, report.comparison.as_of])
        tenant = self._tenant()
        selection = ReportSelection(report_type=report.report_type, dates=dates, nonce=secrets.token_hex(16),
                                    tenant_binding=self._digest("tenant", tenant))
        report.explanation_context = self._serializer.dumps(selection.model_dump(mode="json"))
        for movement in report.movements:
            bound = selection.model_copy(update={"account_binding": self._account(selection, movement.account_id, tenant)})
            movement.explanation_context = self._serializer.dumps(bound.model_dump(mode="json"))
        if len(report.model_dump_json().encode()) > self._result_byte_limit:
            raise ApiError(413, "Report result is too large", "The decorated report exceeds the configured result limit.", False, "Choose a narrower report or inspect it in Xero.")
        return report

    def parse(self, token: str) -> ReportSelection:
        """Validate age, signature, shape and tenant before starting financial reads."""
        try:
            if not isinstance(token, str) or len(token) > 2048:
                raise invalid_context()
            selection = ReportSelection.model_validate(self._serializer.loads(token, max_age=self._max_age))
        except (BadData, ValidationError, TypeError, ValueError) as error:
            raise invalid_context() from error
        if len(selection.dates) != (4 if selection.report_type == "profit_and_loss" else 2):
            raise invalid_context()
        if not hmac.compare_digest(selection.tenant_binding, self._digest("tenant", self._tenant())):
            raise invalid_context()
        return selection

    def _account(self, selection: ReportSelection, identity: str, tenant: str) -> str:
        """Bind identity to this tenant, report, date selection and random nonce."""
        return self._digest("account", tenant, identity, selection.report_type,
                            *[value.isoformat() for value in selection.dates], selection.nonce)

    async def resolve(self, token: str, reports: ReportService):
        """Refetch and match one account by HMAC, never by a positional public row key."""
        selection = self.parse(token)
        tenant = self._tenant()
        if selection.report_type == "profit_and_loss":
            report = await reports.compare_profit_and_loss(*selection.dates, "custom")
        else:
            report = await reports.compare_balance_sheets(*selection.dates, "custom")
        if self._tenant() != tenant:
            raise invalid_context()
        key = None
        if selection.account_binding is not None:
            matches = [row for row in report.movements if hmac.compare_digest(selection.account_binding, self._account(selection, row.account_id, tenant))]
            if len(matches) != 1:
                raise invalid_context()
            key = matches[0].key
        return report, key
