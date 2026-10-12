"""Purpose: Confirm or deny a proposed write. Confirmation is the only chat path that writes to Xero.

Public API:
- router
- action_payload
"""

import json
from typing import Any

from fastapi import APIRouter, Request

from app.actions.payloads import apply_optional_overrides
from app.actions.service import action_payload, existing_action_result, load_action, run_confirmed_action
from app.auth.routes import require_user
from app.db.repository import StoredAction
from app.errors import ApiError
from app.runtime import AppServices

router = APIRouter(prefix="/actions", tags=["actions"])


def _load_action(request: Request, action_id: str) -> tuple[AppServices, StoredAction]:
    """Authenticate the caller and load the durable write receipt."""
    require_user(request)
    services: AppServices = request.app.state.services
    action = load_action(services.actions, action_id, request.app.state.settings.action_execution_timeout_seconds)
    return services, action


@router.get("/{action_id}")
def get_action(action_id: str, request: Request) -> dict[str, object]:
    """Return the current status of a proposed action."""
    _services, action = _load_action(request, action_id)
    return action_payload(action)


@router.post("/{action_id}/confirm")
async def confirm_action(action_id: str, request: Request) -> dict[str, object]:
    """Execute one pending action after the person confirms it."""
    services, action = _load_action(request, action_id)
    if action.status != "pending":
        return existing_action_result(action)
    overrides = await _confirm_overrides(request)
    payload, summary = action.payload, action.summary
    if overrides:
        payload, summary = apply_optional_overrides(action.action_type, action.payload, overrides)
    return await run_confirmed_action(services, action, payload, summary, request.app.state.settings.action_execution_timeout_seconds)


@router.post("/{action_id}/deny")
def deny_action(action_id: str, request: Request) -> dict[str, object]:
    """Mark one pending action as denied without calling Xero."""
    services, action = _load_action(request, action_id)
    if action.status == "denied":
        return action_payload(action)
    if action.status != "pending":
        raise ApiError(409, "Action cannot be denied", f"This action is {action.status}.", False, "Review its current status; execution cannot be undone by denial.")
    result = {
        "action_id": action_id,
        "status": "denied",
        "summary": action.summary,
    }
    stored = services.actions.transition_action(action_id, "pending", "denied", result)
    if stored is None:
        raise ApiError(409, "Action cannot be denied", "Another request already claimed this action.", False, "Review its current status.")
    return action_payload(stored)


async def _confirm_overrides(request: Request) -> dict[str, Any]:
    """Read optional confirm fields, or an empty object when the body is absent."""
    raw = await request.body()
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ApiError(
            422,
            "Confirm body is not JSON",
            "The confirm body must be a JSON object.",
            False,
            "Send email, reference, or due date as a JSON object.",
        ) from error
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ApiError(
            422,
            "Confirm body is not an object",
            "The confirm body must be a JSON object.",
            False,
            "Send email, reference, or due date as a JSON object.",
        )
    return parsed
