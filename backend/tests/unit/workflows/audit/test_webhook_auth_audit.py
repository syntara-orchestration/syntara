"""Unit tests for webhook auth audit event handlers."""

from uuid import uuid4

from syntara.audit.models.audit_event import EventCategory, EventSeverity, EventStatus
from syntara.core.models.principal import PrincipalType
from syntara.workflows.audit.webhook_auth import (
    WebhookAuthFailureEvent,
    WebhookAuthFailureHandler,
    WebhookAuthSuccessEvent,
    WebhookAuthSuccessHandler,
)


class TestWebhookAuthSuccessHandler:
    """Tests for WebhookAuthSuccessHandler audit event mapping."""

    def test_produces_info_security_event(self) -> None:
        event = WebhookAuthSuccessEvent(
            service_account_id=uuid4(),
            webhook_path="test-hook",
            trigger_type="webhook_trigger",
            workflow_id=uuid4(),
        )
        result = WebhookAuthSuccessHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.INFO
        assert result.event_status == EventStatus.SUCCESS
        assert result.event_action == "webhook_auth_success"
        assert "test-hook" in result.event_message

    def test_includes_trigger_type_in_structured_data(self) -> None:
        event = WebhookAuthSuccessEvent(
            service_account_id=uuid4(),
            webhook_path="eda-hook",
            trigger_type="eda_trigger",
            workflow_id=uuid4(),
        )
        result = WebhookAuthSuccessHandler().handle(event)

        assert result.structured_data.model_extra.get("trigger_type") == "eda_trigger"  # type: ignore[union-attr]

    def test_includes_actor_id_and_type(self) -> None:
        sa_id = uuid4()
        event = WebhookAuthSuccessEvent(
            service_account_id=sa_id,
            webhook_path="test-hook",
            trigger_type="webhook_trigger",
            workflow_id=uuid4(),
        )
        result = WebhookAuthSuccessHandler().handle(event)

        assert result.actor_id == sa_id
        assert result.actor_type == PrincipalType.SERVICE_ACCOUNT


class TestWebhookAuthFailureHandler:
    """Tests for WebhookAuthFailureHandler audit event mapping."""

    def test_produces_warning_security_event(self) -> None:
        event = WebhookAuthFailureEvent(
            webhook_path="test-hook",
            trigger_type="webhook_trigger",
            failure_reason="missing_token",
        )
        result = WebhookAuthFailureHandler().handle(event)

        assert result.event_category == EventCategory.SECURITY_EVENT
        assert result.event_severity == EventSeverity.WARNING
        assert result.event_status == EventStatus.ERROR
        assert result.event_action == "webhook_auth_failure"
        assert "missing_token" in result.event_message

    def test_includes_sa_id_when_provided(self) -> None:
        sa_id = uuid4()
        event = WebhookAuthFailureEvent(
            webhook_path="test-hook",
            trigger_type="webhook_trigger",
            failure_reason="sa_not_bound",
            service_account_id=sa_id,
        )
        result = WebhookAuthFailureHandler().handle(event)

        assert result.event_action == "webhook_auth_failure"

    def test_sa_id_defaults_to_none(self) -> None:
        event = WebhookAuthFailureEvent(
            webhook_path="test-hook",
            trigger_type="eda_trigger",
            failure_reason="invalid_token",
        )
        assert event.service_account_id is None
