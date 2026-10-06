"""Purpose: Confirm or deny a proposed write. Confirmation is the only chat path that writes to Xero.

Public API:
- router
- action_payload
"""

from fastapi import APIRouter, Request

from app.actions.executor import execute_action, failure_body
from app.auth.routes import require_user
from app.db.repository import StoredAction
from app.errors import ApiError
from app.runtime import AppServices

router = APIRouter(prefix="/actions", tags=["actions"])


def action_payload(action: StoredAction) -> dict[str, object]:
    """Serialize an action without internal database details beyond its id."""
    return {
        "action_id": action.id,
        "action_type": action.action_type,
        "summary": action.summary,
        "status": action.status,
        "payload": action.payload,
        "result": action.result,
    }


def _pending_action(request: Request, action_id: str) -> tuple[AppServices, StoredAction]:
    """Load a pending action for the signed-in user."""
    require_user(request)
    services: AppServices = request.app.state.services
    action = services.actions.get_action(action_id)
    if action is None:
        raise ApiError(
            404,
            "Action does not exist",
            "That confirmation could not be found.",
            False,
            "Ask the assistant to propose the action again.",
        )
    if action.status != "pending":
        raise ApiError(
            409,
            "Action is already finished",
            f"This action is {action.status}.",
            False,
            "Propose a new action if something else still needs to change.",
        )
    return services, action


@router.get("/{action_id}")
def get_action(action_id: str, request: Request) -> dict[str, object]:
    """Return the current status of a proposed action."""
    require_user(request)
    services: AppServices = request.app.state.services
    action = services.actions.get_action(action_id)
    if action is None:
        raise ApiError(
            404,
            "Action does not exist",
            "That confirmation could not be found.",
            False,
            "Ask the assistant to propose the action again.",
        )
    return action_payload(action)


@router.post("/{action_id}/confirm")
async def confirm_action(action_id: str, request: Request) -> dict[str, object]:
    """Execute one pending action after the person confirms it."""
    services, action = _pending_action(request, action_id)
    try:
        result = await execute_action(action, services.invoices)
    except ApiError as error:
        body = failure_body(action_id, error)
        services.actions.update_action(action_id, "failed", body)
        raise ApiError(error.status_code, error.what, error.why, error.retryable, error.next_step) from error
    result_body = {"action_id": action_id, "summary": action.summary, **result}
    services.actions.update_action(action_id, "executed", result_body)
    return result_body


@router.post("/{action_id}/deny")
def deny_action(action_id: str, request: Request) -> dict[str, object]:
    """Mark one pending action as denied without calling Xero."""
    services, action = _pending_action(request, action_id)
    result = {
        "action_id": action_id,
        "status": "denied",
        "summary": action.summary,
    }
    stored = services.actions.update_action(action_id, "denied", result)
    return action_payload(stored)
