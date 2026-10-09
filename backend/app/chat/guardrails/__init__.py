"""Purpose: Compose secret redaction, the known-phrase screen, and the Jev input screen.

Public API:
- chat_guardrails
"""

from pydantic_ai_harness import InputGuardrail
from pydantic_ai_harness.guardrails.detectors import redact_secrets

from app.chat.guardrails.policy_screen import screen_user_message
from app.chat.guardrails.phrase_screen import screen_known_phrases
from app.chat.guardrails.redaction import PERSONAL_DATA, tool_result_guardrail


def chat_guardrails() -> list[object]:
    """Redact secrets, refuse known phrases, screen with Jev, and redact tool results."""
    return [
        InputGuardrail(
            guard=[redact_secrets, PERSONAL_DATA, screen_known_phrases, screen_user_message]
        ),
        tool_result_guardrail(),
    ]
