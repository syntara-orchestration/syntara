"""Tests for WebhookTriggerParameters model.

Covers:
- Valid webhook path patterns
- Invalid webhook path rejection
- Optional input_schema field
- Template expression bypass
- Required authorized_service_account_ids with min 1 entry
"""

import uuid

import pytest
from pydantic import ValidationError

from syntara.workflows.workflow_engine.models.workflow_definition import WebhookTriggerParameters

SA_ID = uuid.uuid4()


async def test_valid_webhook_path() -> None:
    """Valid webhook paths should be accepted."""
    config = WebhookTriggerParameters(webhook_path="jira-updates", authorized_service_account_ids=[SA_ID])
    assert config.webhook_path == "jira-updates"


async def test_webhook_path_rejects_slashes() -> None:
    """Webhook paths with slashes should be rejected (single-segment only)."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="team/jira-updates", authorized_service_account_ids=[SA_ID])


async def test_valid_webhook_path_with_underscores() -> None:
    """Webhook paths with underscores should be accepted."""
    config = WebhookTriggerParameters(webhook_path="my_webhook_endpoint", authorized_service_account_ids=[SA_ID])
    assert config.webhook_path == "my_webhook_endpoint"


async def test_webhook_path_no_input_schema() -> None:
    """input_schema should default to None."""
    config = WebhookTriggerParameters(webhook_path="test-hook", authorized_service_account_ids=[SA_ID])
    assert config.input_schema is None


async def test_webhook_path_with_input_schema() -> None:
    """input_schema should accept a valid schema dict."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"event": {"type": "string"}},
        "additionalProperties": True,
    }
    config = WebhookTriggerParameters(
        webhook_path="validated", input_schema=schema, authorized_service_account_ids=[SA_ID]
    )
    assert config.input_schema == schema


async def test_webhook_path_single_character() -> None:
    """Single-character paths should be accepted (min_length=1)."""
    config = WebhookTriggerParameters(webhook_path="a", authorized_service_account_ids=[SA_ID])
    assert config.webhook_path == "a"


async def test_webhook_path_single_digit() -> None:
    """Single-digit paths should be accepted."""
    config = WebhookTriggerParameters(webhook_path="7", authorized_service_account_ids=[SA_ID])
    assert config.webhook_path == "7"


async def test_webhook_path_rejects_leading_hyphen() -> None:
    """Paths starting with a hyphen should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="-test", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_rejects_trailing_hyphen() -> None:
    """Paths ending with a hyphen should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="test-", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_rejects_trailing_slash() -> None:
    """Paths ending with a slash should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="test/", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_rejects_uppercase() -> None:
    """Webhook paths with uppercase should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="MyWebhook", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_rejects_spaces() -> None:
    """Webhook paths with spaces should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="my webhook", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_rejects_empty() -> None:
    """Empty webhook paths should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="", authorized_service_account_ids=[SA_ID])


async def test_webhook_path_template_expression_bypass() -> None:
    """Template expressions should bypass validation."""
    config = WebhookTriggerParameters(webhook_path="${input.path}", authorized_service_account_ids=[SA_ID])
    assert config.webhook_path == "${input.path}"


async def test_authorized_service_account_ids_required() -> None:
    """Creating a webhook without authorized_service_account_ids should fail."""
    with pytest.raises(ValidationError, match="authorized_service_account_ids"):
        WebhookTriggerParameters.model_validate({"webhook_path": "test-hook"})


async def test_authorized_service_account_ids_rejects_empty_list() -> None:
    """An empty authorized_service_account_ids list should be rejected."""
    with pytest.raises(ValidationError):
        WebhookTriggerParameters(webhook_path="test-hook", authorized_service_account_ids=[])


async def test_authorized_service_account_ids_accepts_one() -> None:
    """A single service account ID should be accepted."""
    sa = uuid.uuid4()
    config = WebhookTriggerParameters(webhook_path="test-hook", authorized_service_account_ids=[sa])
    assert config.authorized_service_account_ids == [sa]


async def test_authorized_service_account_ids_accepts_multiple() -> None:
    """Multiple service account IDs should be accepted."""
    ids = [uuid.uuid4(), uuid.uuid4()]
    config = WebhookTriggerParameters(webhook_path="test-hook", authorized_service_account_ids=ids)
    assert config.authorized_service_account_ids == ids
