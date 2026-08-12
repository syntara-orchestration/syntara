"""Tests for WebhookTrigger model and WebhookTriggerRead schema.

Covers:
- Model instantiation with valid fields
- Field constraints and defaults
- Trigger type consistency between Python constants and DB constraint
"""

import re
from uuid import uuid4

from sqlalchemy import CheckConstraint

from syntara.workflows.models.webhook_trigger import WebhookTrigger, WebhookTriggerRead
from syntara.workflows.services.webhook_trigger_service import WEBHOOK_TRIGGER_TYPES


async def test_webhook_trigger_creation() -> None:
    """WebhookTrigger should be creatable with required fields."""
    workflow_id = uuid4()
    trigger = WebhookTrigger(
        webhook_path="my-webhook",
        workflow_id=workflow_id,
        trigger_node_id="trigger_webhook_1",
    )

    assert trigger.webhook_path == "my-webhook"
    assert trigger.workflow_id == workflow_id
    assert trigger.trigger_node_id == "trigger_webhook_1"
    assert trigger.is_enabled is True
    assert trigger.input_schema is None


async def test_webhook_trigger_with_input_schema() -> None:
    """WebhookTrigger should accept input_schema."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"event": {"type": "string"}},
    }
    trigger = WebhookTrigger(
        webhook_path="validated-hook",
        workflow_id=uuid4(),
        trigger_node_id="trigger_1",
        input_schema=schema,
    )

    assert trigger.input_schema == schema


async def test_webhook_trigger_read() -> None:
    """WebhookTriggerRead should validate from a WebhookTrigger."""
    trigger = WebhookTrigger(
        webhook_path="test-path",
        workflow_id=uuid4(),
        trigger_node_id="trigger_1",
    )

    read = WebhookTriggerRead.model_validate(trigger)
    assert read.webhook_path == "test-path"


async def test_webhook_trigger_disabled() -> None:
    """WebhookTrigger should support disabled state."""
    trigger = WebhookTrigger(
        webhook_path="disabled-hook",
        workflow_id=uuid4(),
        trigger_node_id="trigger_1",
        is_enabled=False,
    )
    assert trigger.is_enabled is False


def test_check_constraint_matches_webhook_trigger_types() -> None:
    """DB check constraint must list exactly the same types as WEBHOOK_TRIGGER_TYPES."""
    constraints = [arg for arg in WebhookTrigger.__table_args__ if isinstance(arg, CheckConstraint)]
    trigger_type_constraint = next(c for c in constraints if c.name == "ck_webhook_triggers_trigger_type_valid")
    constraint_text = str(trigger_type_constraint.sqltext)
    values_in_constraint = set(re.findall(r"'([^']+)'", constraint_text))
    assert values_in_constraint == set(WEBHOOK_TRIGGER_TYPES), (
        f"CheckConstraint has {values_in_constraint} but WEBHOOK_TRIGGER_TYPES has {set(WEBHOOK_TRIGGER_TYPES)}. "
        "Update both when adding a new trigger type."
    )
