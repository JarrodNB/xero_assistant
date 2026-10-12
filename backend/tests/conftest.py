"""Purpose: Shared fixtures for the API test client.

Public API:
- PASSWORD
- USERNAME
- api
"""

import os
import tempfile
from pathlib import Path

import pytest
import httpx
from pydantic_ai import models
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ["APP_USERNAME"] = "interviewer"
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("MODEL", "openai:gpt-4.1-mini")
os.environ.setdefault("DATABASE_PATH", str(Path(tempfile.gettempdir()) / "xero-assistant-import.db"))
os.environ["APP_PASSWORD_HASH"] = PasswordHasher().hash("interview-secret")

USERNAME = "interviewer"
PASSWORD = "interview-secret"


def pytest_addoption(parser) -> None:
    """Expose deliberate opt-in for paid evaluation tests."""
    parser.addoption("--live-evals", action="store_true", help="Run paid provider evaluations")


def pytest_collection_modifyitems(config, items) -> None:
    """Skip paid cases unless the dedicated opt-in flag is present."""
    if not config.getoption("--live-evals"):
        for item in items:
            if item.get_closest_marker("live_eval"):
                item.add_marker(pytest.mark.skip(reason="Paid evaluation requires --live-evals"))


@pytest.fixture(autouse=True)
def _block_live_models(request, monkeypatch):
    """Prevent accidental real PydanticAI requests in every offline test."""
    permitted = request.config.getoption("--live-evals") and request.node.get_closest_marker("live_eval")
    if not permitted:
        def reject_request(*args, **kwargs):
            """Reject real synchronous HTTP while allowing mock and ASGI transports."""
            raise AssertionError("Offline tests must use a mocked HTTP transport")

        async def reject_async_request(*args, **kwargs):
            """Reject real asynchronous HTTP, including optional Jev providers."""
            raise AssertionError("Offline tests must use a mocked HTTP transport")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_request)
        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject_async_request)
    with models.override_allow_model_requests(bool(permitted)):
        yield


@pytest.fixture(autouse=True)
def _reset_pii_vault():
    """Drop request-scoped guardrail state left by an earlier test."""
    from app.chat.guardrails.context import current_guardrail_context
    from app.chat.guardrails.pii import current_vault

    context_token = current_guardrail_context.set(None)
    vault_token = current_vault.set(None)
    yield
    current_vault.reset(vault_token)
    current_guardrail_context.reset(context_token)


@pytest.fixture
def api(tmp_path: Path):
    """Return a test client signed against an in-memory invoice gateway."""
    from app.config import Settings
    from app.main import create_app
    from tests.fakes import FakeInvoiceGateway

    settings = Settings(
        app_username=USERNAME,
        app_password_hash=os.environ["APP_PASSWORD_HASH"],
        session_secret="test-session-secret",
        database_path=str(tmp_path / "app.db"),
        model="openai:gpt-4.1-mini",
    )
    fake = FakeInvoiceGateway()
    application = create_app(settings=settings, invoices=fake)
    with TestClient(application) as client:
        yield client, fake


def sign_in(client: TestClient) -> None:
    """Create a session with the shared interviewer credentials."""
    response = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert response.status_code == 200
