"""Purpose: Refuse known unsafe phrases in the user message before Jev runs.

Public API:
- screen_known_phrases
"""

import re

from pydantic_ai_harness import GuardrailResult

from app.chat.guardrails.policy_screen import REFUSAL, SUPPORT

_JAILBREAK = (
    re.compile(
        r"\bignore\b(?:\s+\w+){0,3}\s+(?:instructions|rules|prompts)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:disregard|forget|override|bypass)\b(?:\s+\w+){0,4}\s+"
        r"(?:instructions|rules|system prompt|safety rules|guidelines)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|print|show|dump|repeat|output)\b(?:\s+\w+){0,5}\s+"
        r"(?:system prompt|hidden instructions|hidden prompt|system instructions)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:pretend|act|roleplay)\b(?:\s+\w+){0,8}\s+no\s+(?:rules|restrictions|limits|filters)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you are|you're|act as|roleplay as)\b(?:\s+\w+){0,4}\s+"
        r"(?:dan|jailbroken|unfiltered|unrestricted)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byou\s+have\s+no\s+(?:rules|restrictions|limits|filters)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:developer mode|jailbreak|do anything now|dan mode)\b", re.IGNORECASE),
)

_HARM = (
    re.compile(r"\bphysically\s+hurt\b", re.IGNORECASE),
    re.compile(
        r"\b(?:hurt|harm|attack|murder|stab|shoot|kill)\b(?:\s+\w+){0,3}\s+"
        r"(?:someone|somebody|people|him|her|them|a person)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bhow\s+(?:do i|to)\s+(?:make|build|assemble)\b(?:\s+\w+){0,4}\s+"
        r"(?:a\s+|an\s+)?(?:bomb|explosive|weapon|gun|poison)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bhow\s+to\s+(?:kill|murder|poison|stab|shoot)\b", re.IGNORECASE),
    re.compile(r"\b(?:bomb|explosive|weapon)\s+(?:making|instructions)\b", re.IGNORECASE),
)

_DOSAGE = (
    re.compile(r"\bwhat\s+(?:dosage|dose)\b", re.IGNORECASE),
    re.compile(r"\b(?:dosage|dose)\s+of\b", re.IGNORECASE),
    re.compile(r"\bhow\s+many\s+(?:mg|milligrams)\b", re.IGNORECASE),
    re.compile(r"\bshould i take\b", re.IGNORECASE),
)

_SELF_HARM = re.compile(
    r"\b(?:kill myself|killing myself|end my life|ending my life|take my own life|"
    r"taking my own life|suicid(?:e|al)|want to die|self[-\s]?harm|hurt myself|cut myself)\b",
    re.IGNORECASE,
)


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    """Return whether any pattern matches the message."""
    return any(pattern.search(text) for pattern in patterns)


def screen_known_phrases(prompt: str) -> GuardrailResult:
    """Refuse known jailbreak, harm, and dosage phrases, and answer self-harm with the support line."""
    text = prompt.strip()
    if not text:
        return GuardrailResult.allow()
    if _SELF_HARM.search(text):
        return GuardrailResult.block(SUPPORT)
    if _matches(_JAILBREAK, text) or _matches(_HARM, text) or _matches(_DOSAGE, text):
        return GuardrailResult.block(REFUSAL)
    return GuardrailResult.allow()
