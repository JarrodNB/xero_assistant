"""Purpose: Keep rendered report figures out of ordinary model and summary history.

Public API:
- REPORT_HISTORY_NOTICE
- without_report_figures
"""

REPORT_HISTORY_NOTICE = "A report explanation was viewed. Its figures are not retained in chat history. Reopen Performance and select Explain this change to refetch evidence before asking about figures."


def without_report_figures(text: str) -> str:
    """Replace the application-rendered report envelope before any free-prose processing."""
    if "Profit and loss — " in text or "Balance sheet — " in text:
        return REPORT_HISTORY_NOTICE
    return text
