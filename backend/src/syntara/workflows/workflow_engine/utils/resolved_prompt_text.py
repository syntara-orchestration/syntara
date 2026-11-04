"""Shared utilities for processing prompt/message text in workflow nodes.

Used by both approval and form_prompt nodes to safely select, scrub, and
truncate prompt text values. The ordering (select → scrub → coerce+truncate)
is load-bearing for correctness.
"""

import json
from collections.abc import Callable
from typing import Any

from temporalio import workflow


def warn_prompt_coercion(message: str) -> None:
    """Log prompt-coercion issues without crashing outside a workflow context.

    Args:
        message: Warning message to log

    """
    if workflow.in_workflow():
        workflow.logger.warning(message)


def select_prompt_value(resolved_parameters: dict[str, Any], field_name: str) -> Any | None:  # noqa: ANN401
    """Select a prompt/message field value, or None if it is not storable.

    ``NamespaceResolver.resolve_value`` keeps the original type when the whole
    field is a single ``${...}``, so the prompt can arrive as any JSON value.
    Booleans, empty containers and blank strings are not human-readable guidance
    and are dropped here.

    The ``json.dumps`` probe doubles as a **cycle guard**: ``scrub_credentials``
    and ``scrub_credential_values`` recurse through dicts and lists with no cycle
    detection, so a self-referencing template must be rejected *before* it reaches
    the scrubber. Returning a value from this function is the promise that it is
    safe to scrub.

    Args:
        resolved_parameters: Node parameters after template resolution
        field_name: Name of the field to extract (e.g., "prompt", "message")

    Returns:
        The prompt value if it is storable, None otherwise

    """
    prompt = resolved_parameters.get(field_name)
    if prompt is None or isinstance(prompt, bool):
        return None
    if isinstance(prompt, str):
        return prompt.strip() or None
    if isinstance(prompt, (dict, list)):
        if not prompt:
            return None
        try:
            json.dumps(prompt, default=str)
        except (TypeError, ValueError):
            warn_prompt_coercion(f"Could not serialize {field_name}; storing no value")
            return None
    return prompt


def render_prompt_text(
    value: Any,  # noqa: ANN401
    max_length: int,
    field_name: str = "prompt",
) -> str | None:
    """Render an already-scrubbed prompt value to the text that gets stored.

    Runs last so the length cap is applied to the final string. Scrubbing can
    *lengthen* a value — ``[REDACTED]`` is 10 characters and a secret may be as
    short as 4 — so truncating before scrubbing can push the result back over the
    limit and turn ``POST /approvals`` or ``POST /form_prompts`` into a validation
    failure.

    Objects that do not fit are dropped rather than stored as a broken JSON
    fragment. Oversized plain text is truncated with a trailing ellipsis so
    users can see it was clipped.

    Args:
        value: The scrubbed prompt value (can be str, dict, list, or scalar)
        max_length: Maximum allowed string length
        field_name: Name of the field being rendered (for warning messages)

    Returns:
        Rendered text string within max_length, or None if value cannot be rendered

    """
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str)
        if len(text) > max_length:
            warn_prompt_coercion(
                f"{field_name.capitalize()} JSON length {len(text)} exceeds {max_length} characters; storing no value"
            )
            return None
        return text

    text = (value if isinstance(value, str) else str(value)).strip()
    if not text:
        return None
    if len(text) <= max_length:
        return text

    warn_prompt_coercion(f"{field_name.capitalize()} length {len(text)} exceeds {max_length} characters; truncating")
    return text[: max_length - 1] + "…"


def process_prompt_field(
    resolved_parameters: dict[str, Any],
    field_name: str,
    max_length: int,
    scrub_data: Callable[[dict[str, Any]], dict[str, Any]],
) -> str | None:
    """Complete prompt field processing pipeline: select → scrub → render.

    This is the standard entry point that ensures correct ordering of operations.

    Args:
        resolved_parameters: Node parameters after template resolution
        field_name: Name of the field to process (e.g., "prompt", "message")
        max_length: Maximum allowed final string length
        scrub_data: Credential scrubbing function

    Returns:
        Final rendered and truncated text, or None if no storable value

    """
    value = select_prompt_value(resolved_parameters, field_name)
    if value is None:
        return None

    # Scrub credentials: wrap in a dict so scrub_data can process it
    scrubbed = scrub_data({field_name: value})
    scrubbed_value = scrubbed.get(field_name)

    return render_prompt_text(scrubbed_value, max_length, field_name)
