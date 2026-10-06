"""Purpose: Tests for the shared interviewer login.

Public API:
- test_wrong_password_is_rejected
- test_shared_credentials_create_a_session
- test_protected_routes_reject_missing_sessions
- test_logout_clears_the_session
"""

from tests.conftest import USERNAME, sign_in


def test_wrong_password_is_rejected(api) -> None:
    """A wrong password returns one generic failure."""
    client, _fake = api
    response = client.post("/auth/login", json={"username": USERNAME, "password": "nope"})
    assert response.status_code == 401
    body = response.json()
    assert body["what"] == "Login failed"
    assert "password" in body["why"].lower() or "username" in body["why"].lower()


def test_shared_credentials_create_a_session(api) -> None:
    """The interviewer username and password set an httpOnly session cookie."""
    client, _fake = api
    response = client.post("/auth/login", json={"username": USERNAME, "password": "interview-secret"})
    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert "httponly" in response.headers["set-cookie"].lower()
    session = client.get("/auth/session")
    assert session.json()["authenticated"] is True


def test_protected_routes_reject_missing_sessions(api) -> None:
    """Invoice, chat, and action routes stay closed without a session."""
    client, _fake = api
    assert client.get("/invoices").status_code == 401
    assert client.post("/chat", json={}).status_code == 401
    assert client.get("/conversations").status_code == 401
    assert client.get("/conversations/missing").status_code == 401
    assert client.post("/actions/missing/confirm").status_code == 401
    assert client.get("/contacts", params={"name": "Bob"}).status_code == 401


def test_logout_clears_the_session(api) -> None:
    """Logout ends the session."""
    client, _fake = api
    sign_in(client)
    assert client.post("/auth/logout").json()["authenticated"] is False
    assert client.get("/invoices").status_code == 401
