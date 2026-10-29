"""Shared timeout message formatting for workflow execution errors."""

SECONDS_PER_MINUTE = 60


def format_timeout_friendly(seconds: float | None) -> str:
    """Format timeout duration into a concise human-readable string."""
    if not seconds or seconds <= 0:
        return "the configured timeout"

    total = int(seconds)
    if total < SECONDS_PER_MINUTE:
        return f"{total} second{'s' if total != 1 else ''}"

    minutes = total // SECONDS_PER_MINUTE
    remaining_seconds = total % SECONDS_PER_MINUTE
    if remaining_seconds == 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

    minute_part = f"{minutes} minute{'s' if minutes != 1 else ''}"
    second_part = f"{remaining_seconds} second{'s' if remaining_seconds != 1 else ''}"
    return f"{minute_part} {second_part}"


def build_timeout_error_message(
    *,
    step_name: str,
    is_agentic: bool,
    timeout_seconds: float | None,
) -> str:
    """Build user-facing timeout remediation guidance for a workflow step."""
    timeout_friendly = format_timeout_friendly(timeout_seconds)
    step_label = f'The AI Agent step "{step_name}"' if is_agentic else f'The step "{step_name}"'
    guidance = (
        "Increase the timeout, simplify the prompt, or try again. "
        "If the agent may still be running, check execution details before re-running."
        if is_agentic
        else "Increase the timeout in the node settings, or try again."
    )
    return f"{step_label} did not finish within {timeout_friendly} (configured in the node Timeout setting). {guidance}"
