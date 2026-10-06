"""Purpose: Persist the one Xero refresh token and tenant.

Public API:
- XeroConnection
- XeroConnectionStore
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.db.schema import XeroConnectionRow, utcnow


@dataclass(frozen=True)
class XeroConnection:
    """Refresh token and the organisation it authorises."""

    refresh_token: str
    tenant_id: str
    tenant_name: str


class XeroConnectionStore:
    """Read and replace the single Xero connection row."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Keep the session factory for short-lived transactions."""
        self._session_factory = session_factory

    def load(self) -> XeroConnection | None:
        """Return the saved connection, if someone has authorised Xero."""
        with self._session_factory() as session:
            row = session.get(XeroConnectionRow, 1)
            if row is None:
                return None
            return XeroConnection(row.refresh_token, row.tenant_id, row.tenant_name)

    def save(self, connection: XeroConnection) -> None:
        """Insert or replace the saved connection."""
        with self._session_factory() as session:
            row = session.get(XeroConnectionRow, 1)
            if row is None:
                session.add(
                    XeroConnectionRow(
                        id=1,
                        refresh_token=connection.refresh_token,
                        tenant_id=connection.tenant_id,
                        tenant_name=connection.tenant_name,
                    )
                )
            else:
                row.refresh_token = connection.refresh_token
                row.tenant_id = connection.tenant_id
                row.tenant_name = connection.tenant_name
                row.updated_at = utcnow()
            session.commit()
