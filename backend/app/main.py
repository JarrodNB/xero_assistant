"""Purpose: Create the FastAPI application, session cookie, and routers.

Public API:
- create_app
"""

from contextlib import asynccontextmanager, AsyncExitStack

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app.actions.routes import router as actions_router
from app.auth.routes import router as auth_router
from app.chat.orchestrator import build_chat_agent
from app.chat.execution import production_model
from app.chat.routes import router as chat_router
from app.config import Settings, get_settings
from app.db.repository import ActionRepository
from app.db.schema import create_engine_for
from app.errors import ApiError
from app.invoices.routes import router as invoices_router
from app.invoices.xero_service import XeroInvoiceService
from app.mcp_server.server import build_mcp_server
from app.observability import configure_observability
from app.runtime import AppServices
from app.xero.client import XeroClient
from app.xero.connection_store import XeroConnectionStore
from app.xero.routes import router as xero_router


def create_app(
    settings: Settings | None = None,
    invoices: object | None = None,
    agent: object | None = None,
    xero_http: object | None = None,
) -> FastAPI:
    """Build the API with a session cookie and the invoice routes."""
    resolved = settings or get_settings()
    trace_provider = configure_observability(resolved)
    engine = create_engine_for(resolved.database_path)
    session_factory = sessionmaker(bind=engine)
    repository = ActionRepository(session_factory)
    connections = XeroConnectionStore(session_factory)
    xero = XeroClient(resolved.xero_client_id, resolved.xero_client_secret, connections, xero_http)  # type: ignore[arg-type]
    gateway = invoices or XeroInvoiceService(xero)
    mcp_server = build_mcp_server()
    ai_model, ai_client = production_model(resolved) if agent is None else (None, None)
    chat_agent = agent or build_chat_agent(ai_model, mcp_server, resolved)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Release the owned Xero client and database pool when the API stops."""
        async with AsyncExitStack() as resources:
            resources.callback(engine.dispose)
            if trace_provider is not None:
                resources.callback(trace_provider.shutdown)
            resources.push_async_callback(xero.aclose)
            if ai_client is not None:
                resources.push_async_callback(ai_client.close)
            yield

    app = FastAPI(
        title="Xero Assistant",
        lifespan=lifespan,
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
    )
    app.state.settings = resolved
    app.state.xero = xero
    app.state.xero_connections = connections
    app.state.services = AppServices(invoices=gateway, actions=repository)  # type: ignore[arg-type]
    app.state.agent = chat_agent
    app.state.ai_model = ai_model
    app.state.mcp_server = mcp_server
    app.add_middleware(
        SessionMiddleware,
        secret_key=resolved.session_secret,
        session_cookie="xero_assistant_session",
        max_age=60 * 60 * 24 * 14,
        same_site="lax",
        https_only=resolved.session_https_only,
    )
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
    app.include_router(auth_router)
    app.include_router(xero_router)
    app.include_router(invoices_router)
    app.include_router(actions_router)
    app.include_router(chat_router)
    return app


def _api_error(_request: Request, error: Exception) -> JSONResponse:
    """Render an ApiError as JSON."""
    api_error = error if isinstance(error, ApiError) else ApiError(500, "Request failed", "Something went wrong.", False, "Try again.")
    return JSONResponse(
        status_code=api_error.status_code,
        content={
            "what": api_error.what,
            "why": api_error.why,
            "retryable": api_error.retryable,
            "next_step": api_error.next_step,
            "outcome_unknown": api_error.outcome_unknown,
        },
    )


def _request_validation_error(_request: Request, error: Exception) -> JSONResponse:
    """Render request validation without echoing unsafe or non-JSON input values."""
    validation_error = error if isinstance(error, RequestValidationError) else None
    errors = validation_error.errors() if validation_error is not None else []
    why = str(errors[0].get("msg", "The request fields are invalid.")) if errors else "The request fields are invalid."
    return JSONResponse(
        status_code=422,
        content={
            "what": "Request payload is invalid",
            "why": why,
            "retryable": False,
            "next_step": "Correct the invalid fields and try again.",
        },
    )


app = create_app()
