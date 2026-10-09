"""Purpose: Compose personal-data protection, secret redaction, the known-phrase screen, and the Jev input screen.

Public API:
- chat_guardrails
"""

from pydantic_ai_harness import InputGuardrail
from pydantic_ai_harness.guardrails.detectors import redact_secrets

from app.chat.guardrails.policy_screen import screen_user_message
from app.chat.guardrails.phrase_screen import screen_known_phrases
from app.chat.guardrails.redaction import protect_prompt, tool_result_guardrail


def chat_guardrails() -> list[object]:
    """Protect personal data, redact secrets, refuse known phrases, screen with Jev, and guard tools."""
    return [
        InputGuardrail(
            guard=[protect_prompt, redact_secrets, screen_known_phrases, screen_user_message]
        ),
        tool_result_guardrail(),
    ]
