"""Purpose: Share durable execution and recovery between chat confirmations and editor writes.

Public API:
- action_payload
- existing_action_result
- load_action
- run_confirmed_action
"""

import asyncio
import logging
from datetime import timedelta
from typing import Any

from app.actions.executor import execute_action, failure_body
from app.db.repository import ActionRepository, StoredAction
from app.db.schema import utcnow
from app.errors import ApiError
from app.runtime import AppServices
from app.xero.client import current_write_key

logger = logging.getLogger(__name__)
UNKNOWN_NEXT_STEP = "Check Xero before submitting another write; this action will not be replayed."


def action_payload(action: StoredAction) -> dict[str, object]:
    """Serialize a durable action receipt without database storage details."""
    return {
        "action_id": action.id,
        "action_type": action.action_type,
        "summary": action.summary,
        "status": action.status,
        "payload": action.payload,
        "result": action.result,
    }


def load_action(actions: ActionRepository, action_id: str, timeout_seconds: float) -> StoredAction:
    """Quarantine expired claims and return the action without ever replaying a write."""
    actions.recover_stale_action(action_id, utcnow() - timedelta(seconds=timeout_seconds + 60))
    action = actions.get_action(action_id)
    if action is None:
        raise ApiError(404, "Action does not exist", "That write receipt could not be found.", False, "Review the conversation or submit a new intentional action.")
    return action


def existing_action_result(action: StoredAction) -> dict[str, object]:
    """Replay successful local results and report in-flight or uncertain writes."""
    if action.status == "executed" and action.result is not None:
        return action.result
    if action.status in {"executing", "unknown"}:
        return {
            **action_payload(action),
            "retryable": False,
            "next_step": "Wait for the result." if action.status == "executing" else UNKNOWN_NEXT_STEP,
        }
    raise ApiError(409, "Action is already finished", f"This action is {action.status}.", False, "Review the recorded result before submitting another action.")


def _unknown_error(why: str) -> ApiError:
    """Create a sanitized error that never recommends replaying an uncertain write."""
    return ApiError(502, "Execution outcome is unknown", why, False, UNKNOWN_NEXT_STEP, outcome_unknown=True)


def _record_failure(actions: ActionRepository, action_id: str, error: ApiError) -> None:
    """Persist a failure, retaining the original durable claim if persistence is unavailable."""
    body = failure_body(action_id, error)
    try:
        actions.transition_action(action_id, "executing", str(body["status"]), body)
    except Exception as persistence_error:
        logger.error("Could not record action outcome (%s).", type(persistence_error).__name__)
        raise _unknown_error("The server could not save a final execution result.") from persistence_error


async def run_confirmed_action(
    services: AppServices,
    action: StoredAction,
    payload: dict[str, Any],
    summary: str,
    timeout_seconds: float,
) -> dict[str, object]:
    """Freeze and execute one human-confirmed write, bounded by a durable claim and deadline."""
    if action.status != "pending":
        return existing_action_result(action)
    claimed = services.actions.claim_action(action, payload, summary)
    if claimed is None:
        return existing_action_result(load_action(services.actions, action.id, timeout_seconds))
    action = claimed
    key_token = current_write_key.set(f"ledger-action-{action.id}")
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await execute_action(action, services.invoices)
    except ApiError as error:
        _record_failure(services.actions, action.id, error)
        raise
    except asyncio.CancelledError:
        try:
            _record_failure(services.actions, action.id, _unknown_error("Execution was interrupted before a final result was recorded."))
        except ApiError:
            pass  # The durable executing claim remains quarantined on a later read.
        raise
    except Exception as error:
        logger.error("Action execution stopped (%s).", type(error).__name__)
        unknown = _unknown_error("Execution stopped before a reliable final result was recorded.")
        _record_failure(services.actions, action.id, unknown)
        raise unknown from error
    finally:
        current_write_key.reset(key_token)
    result_body = {"action_id": action.id, "summary": action.summary, **result}
    try:
        stored = services.actions.transition_action(action.id, "executing", "executed", result_body)
    except Exception as error:
        logger.error("Could not persist a successful write (%s).", type(error).__name__)
        raise _unknown_error("Xero returned a result, but the server could not save it.") from error
    if stored is None:
        return existing_action_result(load_action(services.actions, action.id, timeout_seconds))
    return result_body
