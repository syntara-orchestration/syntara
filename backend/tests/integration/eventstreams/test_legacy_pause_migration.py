"""Clear legacy pauses only when workflow publication still desires consumption."""

import importlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Connection

from syntara.eventstreams.models.subscription import EventSubscription
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from tests.integration.eventstreams.conftest import DeliveryContext

pytestmark = pytest.mark.integration
MIGRATION = "syntara.core.database.migrations.versions.d2a6c84e9b10_clear_legacy_published_subscription_pauses"


@pytest.mark.parametrize("state", ["active", "unpaused", "disabled", "retired", "unpublished", "stale_publication"])
async def test_upgrade_clears_only_active_published_pauses(delivery_context: DeliveryContext, state: str) -> None:
    migration = importlib.import_module(MIGRATION)

    def upgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    async with delivery_context.session_factory() as session, session.begin():
        subscription = await session.get(EventSubscription, delivery_context.snapshot.subscription_id)
        workflow = await session.get(Workflow, delivery_context.snapshot.workflow_id)
        assert subscription is not None
        assert workflow is not None
        subscription.paused = state != "unpaused"
        if state == "disabled":
            subscription.desired_enabled = False
        elif state == "retired":
            subscription.retired = True
        elif state == "unpublished":
            workflow.is_enabled = False
            workflow.published_version_id = None
        elif state == "stale_publication":
            version = await session.get(WorkflowVersion, subscription.published_version_id)
            assert version is not None
            replacement = WorkflowVersion(
                workflow_id=workflow.id,
                version=version.version + 1,
                schema_version=version.schema_version,
                workflow_definition=version.workflow_definition,
                created_by=version.created_by,
            )
            session.add(replacement)
            await session.flush()
            workflow.published_version_id = replacement.id
        await session.flush()
        before = subscription.model_dump()
        connection = await session.connection()
        await connection.run_sync(upgrade)
        await session.refresh(subscription)
        expected = dict(before)
        if state == "active":
            expected["paused"] = False
            expected["configuration_revision"] = before["configuration_revision"] + 1
        assert subscription.model_dump() == expected

        # A repeated upgrade must not increase the revision again.
        await connection.run_sync(upgrade)
        await session.refresh(subscription)
        assert subscription.model_dump() == expected
