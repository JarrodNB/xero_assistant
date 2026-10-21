"""Purpose: Synthetic per-case financial fixtures for invoices evaluations.

Public API:
- financial_gateway
"""

from datetime import date
from decimal import Decimal

from app.invoices.gateway import InvoiceReadResult
from app.invoices.records import InvoiceRecord
from tests.fakes import FakeInvoiceGateway


class IncompleteGateway(FakeInvoiceGateway):
    """Represent a bounded read that cannot establish totals or absence."""

    async def find_invoices(self, *args) -> InvoiceReadResult:
        """Return a partial empty subset to exercise absence safety."""
        self.read_calls.append("find_invoices")
        return InvoiceReadResult([], False, 2000)


def financial_gateway(scenario: str | None) -> FakeInvoiceGateway:
    """Build a fresh gateway for each case so concurrent fixtures cannot leak."""
    if scenario == "truncated":
        return IncompleteGateway()
    gateway = FakeInvoiceGateway()
    if scenario == "mixed":
        gateway.invoices = [InvoiceRecord(
            f"INV-{index}", "Synthetic Customer", "AUTHORISED", issued, date(2026, 1, 20),
            Decimal("100"), Decimal("100"), currency, None,
        ) for index, currency, issued in [
            (1, "USD", date(2026, 1, 15)), (2, "AUD", date(2026, 2, 15)),
        ]]
    elif scenario not in (None, "empty"):
        raise ValueError("Unknown financial evaluation fixture")
    return gateway
