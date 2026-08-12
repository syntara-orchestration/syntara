"""Tests for WebhookTriggerParameters model.

Covers:
- Valid webhook path patterns
- Invalid webhook path rejection
- Optional input_schema field
- Template expression bypass
"""

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import WebhookTriggerParameters


async def test_valid_webhook_path() -> None:
    """Valid webhook paths should be accepted."""
    config = WebhookTriggerParameters(webhook_path="jira-updates")
    assert config.webhook_path == "jira-updates"


async def test_webhook_path_rejects_slashes() -> None:
    """Webhook paths with slashes should be rejected (single-segment only)."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="team/jira-updates")


async def test_valid_webhook_path_with_underscores() -> None:
    """Webhook paths with underscores should be accepted."""
    config = WebhookTriggerParameters(webhook_path="my_webhook_endpoint")
    assert config.webhook_path == "my_webhook_endpoint"


async def test_webhook_path_no_input_schema() -> None:
    """input_schema should default to None."""
    config = WebhookTriggerParameters(webhook_path="test-hook")
    assert config.input_schema is None


async def test_webhook_path_with_input_schema() -> None:
    """input_schema should accept a valid schema dict."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"event": {"type": "string"}},
        "additionalProperties": True,
    }
    config = WebhookTriggerParameters(webhook_path="validated", input_schema=schema)
    assert config.input_schema == schema


async def test_webhook_path_single_character() -> None:
    """Single-character paths should be accepted (min_length=1)."""
    config = WebhookTriggerParameters(webhook_path="a")
    assert config.webhook_path == "a"


async def test_webhook_path_single_digit() -> None:
    """Single-digit paths should be accepted."""
    config = WebhookTriggerParameters(webhook_path="7")
    assert config.webhook_path == "7"


async def test_webhook_path_rejects_leading_hyphen() -> None:
    """Paths starting with a hyphen should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="-test")


async def test_webhook_path_rejects_trailing_hyphen() -> None:
    """Paths ending with a hyphen should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="test-")


async def test_webhook_path_rejects_trailing_slash() -> None:
    """Paths ending with a slash should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="test/")


async def test_webhook_path_rejects_uppercase() -> None:
    """Webhook paths with uppercase should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="MyWebhook")


async def test_webhook_path_rejects_spaces() -> None:
    """Webhook paths with spaces should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="my webhook")


async def test_webhook_path_rejects_empty() -> None:
    """Empty webhook paths should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="")


async def test_webhook_path_template_expression_bypass() -> None:
    """Template expressions should bypass validation."""
    config = WebhookTriggerParameters(webhook_path="${input.path}")
    assert config.webhook_path == "${input.path}"
