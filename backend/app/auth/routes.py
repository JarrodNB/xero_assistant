"""Purpose: Login, logout, and session lookup for the shared interviewer account.

Public API:
- router
- require_user
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.auth.passwords import credentials_match
from app.config import Settings
from app.errors import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Username and password submitted from the login page."""

    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=500)


def require_user(request: Request) -> str:
    """Return the session username or reject the request."""
    settings: Settings = request.app.state.settings
    username = request.session.get("user")
    if username != settings.app_username:
        raise ApiError(
            401,
            "Sign in required",
            "This request has no valid session.",
            False,
            "Sign in with the interviewer username and password.",
        )
    return str(username)


@router.post("/login")
def login(body: LoginRequest, request: Request) -> dict[str, bool]:
    """Start a session when the shared credentials match."""
    settings: Settings = request.app.state.settings
    if not credentials_match(body.username, body.password, settings):
        raise ApiError(
            401,
            "Login failed",
            "The username or password was not recognised.",
            True,
            "Check the credentials you were given and try again.",
        )
    request.session["user"] = settings.app_username
    return {"authenticated": True}


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    """Clear the session cookie contents."""
    request.session.clear()
    return {"authenticated": False}


@router.get("/session")
def session(request: Request) -> dict[str, bool]:
    """Report whether the current cookie is signed in."""
    settings: Settings = request.app.state.settings
    return {"authenticated": request.session.get("user") == settings.app_username}
