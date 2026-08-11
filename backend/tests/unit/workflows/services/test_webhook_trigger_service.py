"""Unit tests for WebhookTriggerService.

Tests verify the business logic for webhook trigger management:
path lookup, sync from workflow definitions, and cascade delete.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.exceptions import (
    TriggerValidationError,
    WebhookServiceAccountNotAuthorizedError,
    WebhookTriggerNotFoundError,
    WebhookTriggerPathConflictError,
)
from syntara.workflows.models.webhook_trigger import WebhookTrigger, WebhookTriggerRead
from syntara.workflows.services.webhook_trigger_service import WebhookTriggerService
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType

# ============================================================================
# Helpers
# ============================================================================


def _make_trigger(
    *,
    trigger_node_id: str = "trigger-1",
    webhook_path: str = "test-hook",
    workflow_id: UUID | None = None,
) -> WebhookTrigger:
    """Create a WebhookTrigger instance with sensible defaults."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return WebhookTrigger(
        id=uuid4(),
        webhook_path=webhook_path,
        workflow_id=workflow_id or uuid4(),
        trigger_node_id=trigger_node_id,
        input_schema=None,
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _make_service(
    session: AsyncSession | None = None,
    user: User | None = None,
) -> WebhookTriggerService:
    """Create a WebhookTriggerService with mock session and user."""
    if session is None:
        session = AsyncMock(spec=AsyncSession)
    if user is None:
        user = Mock(spec=User)
        user.id = uuid4()
    return WebhookTriggerService(session=session, user=user)


def _make_workflow_definition(triggers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a minimal workflow definition with optional trigger nodes."""
    return {
        "triggers": triggers or [],
        "nodes": [],
        "edges": [],
    }


# ============================================================================
# Init
# ============================================================================


class TestWebhookTriggerServiceInit:
    """Test WebhookTriggerService initialization."""

    def test_init_with_session_and_user(self) -> None:
        """Test initialization stores session and user."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        service = WebhookTriggerService(session=mock_session, user=mock_user)

        assert service.session is mock_session
        assert service.user is mock_user


# ============================================================================
# get_by_webhook_path
# ============================================================================


class TestGetByWebhookPath:
    """Test suite for get_by_webhook_path."""

    @pytest.mark.asyncio
    async def test_returns_trigger_when_found(self) -> None:
        """Test that an enabled trigger is returned for a matching path."""
        mock_session = AsyncMock(spec=AsyncSession)
        trigger = _make_trigger(webhook_path="github-events")

        mock_result = Mock()
        mock_result.one_or_none.return_value = trigger
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)
        result = await service.get_by_webhook_path("github-events")

        assert result is trigger
        mock_session.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_not_found_when_missing(self) -> None:
        """Test that WebhookTriggerNotFoundError is raised when no trigger matches."""
        mock_session = AsyncMock(spec=AsyncSession)

        mock_result = Mock()
        mock_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        with pytest.raises(WebhookTriggerNotFoundError):
            await service.get_by_webhook_path("nonexistent")

    @pytest.mark.asyncio
    async def test_not_found_error_contains_path(self) -> None:
        """Test that the error contains the webhook path."""
        mock_session = AsyncMock(spec=AsyncSession)

        mock_result = Mock()
        mock_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        with pytest.raises(WebhookTriggerNotFoundError) as exc_info:
            await service.get_by_webhook_path("my-missing-hook")

        assert exc_info.value.webhook_path == "my-missing-hook"

    @pytest.mark.asyncio
    async def test_raises_not_found_when_workflow_disabled(self) -> None:
        """Trigger for a disabled workflow should return not-found.

        The query joins on the Workflow table and filters on
        Workflow.is_enabled, so a trigger whose parent workflow is
        disabled will not be returned.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        mock_result = Mock()
        mock_result.one_or_none.return_value = None  # join excludes disabled workflow
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        with pytest.raises(WebhookTriggerNotFoundError):
            await service.get_by_webhook_path("disabled-workflow-hook")

    @pytest.mark.asyncio
    async def test_returns_eda_trigger_when_found(self) -> None:
        """Test that an EDA trigger is returned when queried with trigger_type=eda_trigger."""
        mock_session = AsyncMock(spec=AsyncSession)
        trigger = _make_trigger(webhook_path="eda-hook")
        trigger.trigger_type = NodeType.EDA_TRIGGER

        mock_result = Mock()
        mock_result.one_or_none.return_value = trigger
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)
        result = await service.get_by_webhook_path("eda-hook", trigger_type=NodeType.EDA_TRIGGER)

        assert result is trigger
        mock_session.exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_not_found_when_workflow_deleted(self) -> None:
        """Trigger for a soft-deleted workflow should return not-found.

        The query joins on the Workflow table and filters on
        Workflow.deleted_at IS NULL, so a trigger whose parent workflow
        is soft-deleted will not be returned.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        mock_result = Mock()
        mock_result.one_or_none.return_value = None  # join excludes deleted workflow
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        with pytest.raises(WebhookTriggerNotFoundError):
            await service.get_by_webhook_path("deleted-workflow-hook")


# ============================================================================
# verify_service_account_authorization
# ============================================================================


class TestVerifyServiceAccountAuthorization:
    """Test suite for verify_service_account_authorization."""

    async def test_authorized_sa_passes(self) -> None:
        """No exception when the SA is bound to the trigger."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.one_or_none.return_value = Mock()  # binding exists
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)
        await service.verify_service_account_authorization(uuid4(), uuid4())

    async def test_unauthorized_sa_raises(self) -> None:
        """WebhookServiceAccountNotAuthorizedError when SA is not bound."""
        trigger_id = uuid4()
        sa_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)

        # First exec: binding lookup returns None
        binding_result = Mock()
        binding_result.one_or_none.return_value = None

        # Second call: session.get returns a trigger for the error message
        trigger = _make_trigger(webhook_path="test-hook")
        mock_session.exec = AsyncMock(return_value=binding_result)
        mock_session.get = AsyncMock(return_value=trigger)

        service = _make_service(session=mock_session)

        with pytest.raises(WebhookServiceAccountNotAuthorizedError) as exc_info:
            await service.verify_service_account_authorization(trigger_id, sa_id)

        assert exc_info.value.webhook_path == "test-hook"

    async def test_unauthorized_sa_with_missing_trigger_uses_unknown(self) -> None:
        """Error uses '<unknown>' when trigger cannot be found for the message."""
        mock_session = AsyncMock(spec=AsyncSession)

        binding_result = Mock()
        binding_result.one_or_none.return_value = None
        mock_session.exec = AsyncMock(return_value=binding_result)
        mock_session.get = AsyncMock(return_value=None)

        service = _make_service(session=mock_session)
        trigger_id = uuid4()
        sa_id = uuid4()

        with pytest.raises(WebhookServiceAccountNotAuthorizedError) as exc_info:
            await service.verify_service_account_authorization(trigger_id, sa_id)

        assert exc_info.value.webhook_path == "<unknown>"


# ============================================================================
# sync_webhook_triggers
# ============================================================================


class TestSyncWebhookTriggers:
    """Test suite for sync_webhook_triggers."""

    @pytest.mark.asyncio
    async def test_creates_new_trigger(self) -> None:
        """Test that a new trigger is created for a webhook node not in the DB."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []  # No existing triggers
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        workflow_id = uuid4()
        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "new-hook"},
                }
            ]
        )

        results = await service.sync_webhook_triggers(workflow_id, definition)

        assert len(results) == 1
        assert isinstance(results[0], WebhookTriggerRead)
        assert results[0].webhook_path == "new-hook"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_trigger(self) -> None:
        """Test that an existing trigger is updated when the node still exists."""
        existing = _make_trigger(
            trigger_node_id="trigger-1",
            webhook_path="old-path",
        )

        mock_session = AsyncMock(spec=AsyncSession)
        # First exec: existing triggers lookup; second exec: SA binding lookup
        existing_result = Mock()
        existing_result.all.return_value = [existing]
        sa_result = Mock()
        sa_result.all.return_value = []
        mock_session.exec = AsyncMock(side_effect=[existing_result, sa_result])
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "new-path"},
                }
            ]
        )

        results = await service.sync_webhook_triggers(existing.workflow_id, definition)

        assert len(results) == 1
        assert results[0].webhook_path == "new-path"

    @pytest.mark.asyncio
    async def test_deletes_removed_trigger(self) -> None:
        """Test that triggers whose nodes were removed are deleted."""
        existing = _make_trigger(trigger_node_id="old-trigger")

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = [existing]
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        # Definition with no triggers — old-trigger should be deleted
        definition = _make_workflow_definition(triggers=[])

        results = await service.sync_webhook_triggers(existing.workflow_id, definition)

        assert len(results) == 0
        mock_session.delete.assert_awaited_once_with(existing)

    @pytest.mark.asyncio
    async def test_path_conflict_extracts_conflicting_path(self) -> None:
        """Test that the actual conflicting path is extracted from PostgreSQL DETAIL."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError(
                "INSERT",
                {},
                Exception(
                    'duplicate key value violates unique constraint "ix_webhook_triggers_type_path_unique"\n'
                    "DETAIL:  Key (trigger_type, webhook_path)=(webhook_trigger, duplicate-path) already exists."
                ),
            )
        )
        mock_session.rollback = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "duplicate-path"},
                },
                {
                    "id": "trigger-2",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "innocent-path"},
                },
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(WebhookTriggerPathConflictError) as exc_info:
            await service.sync_webhook_triggers(workflow_id, definition)

        # Only the conflicting path is reported, not all paths
        assert exc_info.value.webhook_path == "duplicate-path"
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_path_conflict_fallback_when_detail_unparseable(self) -> None:
        """Test that fallback to '<unknown>' is used when DETAIL cannot be parsed."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError(
                "INSERT",
                {},
                Exception("ix_webhook_triggers_type_path_unique"),
            )
        )
        mock_session.rollback = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "some-path"},
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(WebhookTriggerPathConflictError) as exc_info:
            await service.sync_webhook_triggers(workflow_id, definition)

        assert exc_info.value.webhook_path == "<unknown>"
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_webhook_triggers_ignored(self) -> None:
        """Test that non-webhook trigger nodes are ignored."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "manual_trigger",
                    "parameters": {},
                },
                {
                    "id": "trigger-2",
                    "type": "schedule_trigger",
                    "parameters": {},
                },
            ]
        )

        results = await service.sync_webhook_triggers(uuid4(), definition)

        assert len(results) == 0
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_definition(self) -> None:
        """Test sync with a definition that has no triggers at all."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition: dict[str, Any] = {"nodes": [], "edges": []}

        results = await service.sync_webhook_triggers(uuid4(), definition)

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_non_path_integrity_error_reraises(self) -> None:
        """Test that IntegrityError not related to webhook_path is re-raised as-is."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock(
            side_effect=IntegrityError(
                "INSERT",
                {},
                Exception("some_other_constraint"),
            )
        )
        mock_session.rollback = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "test"},
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(IntegrityError):
            await service.sync_webhook_triggers(workflow_id, definition)

    @pytest.mark.asyncio
    async def test_create_and_update_mixed(self) -> None:
        """Test sync with both new and existing trigger nodes."""
        existing = _make_trigger(
            trigger_node_id="trigger-1",
            webhook_path="existing-path",
        )

        mock_session = AsyncMock(spec=AsyncSession)
        # First exec: existing triggers; then two SA binding lookups (one per trigger)
        existing_result = Mock()
        existing_result.all.return_value = [existing]
        sa_result1 = Mock()
        sa_result1.all.return_value = []
        sa_result2 = Mock()
        sa_result2.all.return_value = []
        mock_session.exec = AsyncMock(side_effect=[existing_result, sa_result1, sa_result2])
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "updated-path"},
                },
                {
                    "id": "trigger-2",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "brand-new"},
                },
            ]
        )

        results = await service.sync_webhook_triggers(existing.workflow_id, definition)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_input_schema_stored_on_create(self) -> None:
        """Test that input_schema from the parameters is stored on the new trigger."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        schema = {"type": "object", "required": ["event"]}
        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "with-schema", "input_schema": schema},
                }
            ]
        )

        results = await service.sync_webhook_triggers(uuid4(), definition)

        assert len(results) == 1
        assert results[0].input_schema == schema

    @pytest.mark.asyncio
    async def test_missing_webhook_path_raises_validation_error(self) -> None:
        """Test that a trigger parameters with no webhook_path raises TriggerValidationError."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {},
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(TriggerValidationError, match="trigger-1"):
            await service.sync_webhook_triggers(workflow_id, definition)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_webhook_path_raises_validation_error(self) -> None:
        """Test that a trigger parameters with empty webhook_path raises TriggerValidationError."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": ""},
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(TriggerValidationError, match="trigger-1"):
            await service.sync_webhook_triggers(workflow_id, definition)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_webhook_path_pattern_raises_validation_error(self) -> None:
        """Test that a trigger parameters with invalid path pattern raises TriggerValidationError."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "-invalid-path-"},
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(TriggerValidationError, match="trigger-1"):
            await service.sync_webhook_triggers(workflow_id, definition)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_schema_with_ref_raises_validation_error(self) -> None:
        """Test that a schema containing $ref is rejected at definition time."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {
                        "webhook_path": "test-hook",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "data": {"$ref": "http://internal/schema"},
                            },
                        },
                    },
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(TriggerValidationError, match="trigger-1"):
            await service.sync_webhook_triggers(workflow_id, definition)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_eda_trigger(self) -> None:
        """Test that an EDA trigger is created when trigger_type=eda_trigger."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "eda-1",
                    "type": "eda_trigger",
                    "parameters": {"webhook_path": "jira-updates"},
                }
            ]
        )

        results = await service.sync_webhook_triggers(
            uuid4(),
            definition,
            trigger_type=NodeType.EDA_TRIGGER,
        )

        assert len(results) == 1
        assert results[0].webhook_path == "jira-updates"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_eda_trigger_with_input_schema(self) -> None:
        """Test that input_schema is stored on EDA triggers."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        schema = {"type": "object", "required": ["event"]}
        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "eda-1",
                    "type": "eda_trigger",
                    "parameters": {"webhook_path": "with-schema", "input_schema": schema},
                }
            ]
        )

        results = await service.sync_webhook_triggers(
            uuid4(),
            definition,
            trigger_type=NodeType.EDA_TRIGGER,
        )

        assert len(results) == 1
        assert results[0].input_schema == schema

    @pytest.mark.asyncio
    async def test_schema_with_dangerous_pattern_raises_validation_error(self) -> None:
        """Test that a schema with a ReDoS pattern is rejected at definition time."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "trigger-1",
                    "type": "webhook_trigger",
                    "parameters": {
                        "webhook_path": "test-hook",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "data": {"type": "string", "pattern": "(a+)+$"},
                            },
                        },
                    },
                }
            ]
        )

        workflow_id = uuid4()
        with pytest.raises(TriggerValidationError, match="trigger-1"):
            await service.sync_webhook_triggers(workflow_id, definition)

        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_filters_by_trigger_type(self) -> None:
        """Sync with trigger_type only processes matching trigger nodes."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)

        definition = _make_workflow_definition(
            triggers=[
                {
                    "id": "wh-1",
                    "type": "webhook_trigger",
                    "parameters": {"webhook_path": "generic-hook"},
                },
                {
                    "id": "eda-1",
                    "type": "eda_trigger",
                    "parameters": {"webhook_path": "eda-hook"},
                },
            ]
        )

        results = await service.sync_webhook_triggers(
            uuid4(),
            definition,
            trigger_type=NodeType.EDA_TRIGGER,
        )

        assert len(results) == 1
        assert results[0].webhook_path == "eda-hook"
        assert results[0].trigger_type == NodeType.EDA_TRIGGER


# ============================================================================
# delete_triggers_for_workflow
# ============================================================================


class TestDeleteTriggersForWorkflow:
    """Test suite for delete_triggers_for_workflow."""

    @pytest.mark.asyncio
    async def test_deletes_existing_triggers(self) -> None:
        """Test deletion of all triggers for a workflow."""
        workflow_id = uuid4()
        triggers = [
            _make_trigger(workflow_id=workflow_id, trigger_node_id="t1"),
            _make_trigger(workflow_id=workflow_id, trigger_node_id="t2"),
        ]

        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = triggers
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        service = _make_service(session=mock_session)
        count = await service.delete_triggers_for_workflow(workflow_id)

        assert count == 2
        assert mock_session.delete.await_count == 2
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_triggers(self) -> None:
        """Test that zero is returned when no triggers exist for the workflow."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_result)

        service = _make_service(session=mock_session)
        count = await service.delete_triggers_for_workflow(uuid4())

        assert count == 0
        mock_session.delete.assert_not_called()
        mock_session.flush.assert_not_called()


# ============================================================================
# _sync_trigger_sa_bindings
# ============================================================================


class TestSyncTriggerSaBindings:
    """Test suite for _sync_trigger_sa_bindings."""

    @pytest.mark.asyncio
    async def test_no_op_when_desired_and_existing_match(self) -> None:
        """No DB changes when desired SA IDs equal existing bindings."""
        from syntara.workflows.models.webhook_trigger_service_account import WebhookTriggerServiceAccount

        sa_id = uuid4()
        trigger_id = uuid4()
        workflow_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        existing_link = Mock(spec=WebhookTriggerServiceAccount)
        existing_link.service_account_id = sa_id
        existing_result = Mock()
        existing_result.all.return_value = [existing_link]
        # First exec: SA existence check; second exec: existing bindings
        sa_check_result = Mock()
        sa_check_result.all.return_value = [sa_id]
        mock_workflow = Mock()
        mock_workflow.project_id = uuid4()
        mock_session.exec = AsyncMock(side_effect=[sa_check_result, existing_result])
        mock_session.get = AsyncMock(return_value=mock_workflow)

        service = _make_service(session=mock_session)
        await service._sync_trigger_sa_bindings(trigger_id, {sa_id}, workflow_id)

        mock_session.add.assert_not_called()
        mock_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_new_binding(self) -> None:
        """New SA binding is inserted when not already present."""
        sa_id = uuid4()
        trigger_id = uuid4()
        workflow_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        sa_check_result = Mock()
        sa_check_result.all.return_value = [sa_id]
        existing_result = Mock()
        existing_result.all.return_value = []
        mock_workflow = Mock()
        mock_workflow.project_id = uuid4()
        mock_session.exec = AsyncMock(side_effect=[sa_check_result, existing_result])
        mock_session.get = AsyncMock(return_value=mock_workflow)

        service = _make_service(session=mock_session)
        await service._sync_trigger_sa_bindings(trigger_id, {sa_id}, workflow_id)

        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_stale_binding(self) -> None:
        """Stale SA binding is deleted when no longer in desired set."""
        from syntara.workflows.models.webhook_trigger_service_account import WebhookTriggerServiceAccount

        stale_sa_id = uuid4()
        trigger_id = uuid4()
        workflow_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        existing_link = Mock(spec=WebhookTriggerServiceAccount)
        existing_link.service_account_id = stale_sa_id
        existing_result = Mock()
        existing_result.all.return_value = [existing_link]
        mock_session.exec = AsyncMock(return_value=existing_result)

        service = _make_service(session=mock_session)
        await service._sync_trigger_sa_bindings(trigger_id, set(), workflow_id)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_when_sa_not_found_in_project(self) -> None:
        """TriggerValidationError raised when SA ID doesn't exist in the project."""
        sa_id = uuid4()
        trigger_id = uuid4()
        workflow_id = uuid4()

        mock_session = AsyncMock(spec=AsyncSession)
        sa_check_result = Mock()
        sa_check_result.all.return_value = []  # SA not found
        mock_workflow = Mock()
        mock_workflow.project_id = uuid4()
        mock_session.exec = AsyncMock(return_value=sa_check_result)
        mock_session.get = AsyncMock(return_value=mock_workflow)

        service = _make_service(session=mock_session)

        with pytest.raises(TriggerValidationError, match="not found in this project"):
            await service._sync_trigger_sa_bindings(trigger_id, {sa_id}, workflow_id)

    @pytest.mark.asyncio
    async def test_empty_desired_set_is_no_op(self) -> None:
        """No SA validation or changes when desired set is empty."""
        mock_session = AsyncMock(spec=AsyncSession)
        existing_result = Mock()
        existing_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=existing_result)

        service = _make_service(session=mock_session)
        await service._sync_trigger_sa_bindings(uuid4(), set(), uuid4())

        mock_session.add.assert_not_called()
        mock_session.execute.assert_not_called()
