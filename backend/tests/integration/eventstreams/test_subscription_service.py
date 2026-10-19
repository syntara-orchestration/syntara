"""DB-backed behavior of the event-subscription publication projection.

Exercises the EventSubscriptionService against an isolated per-test database:
publication create/update/retire, identity and group preservation, revision
changes, source replacement, unpublish, snapshots, conservative deletion guards,
and the absence of account-binding/standing-execution gates.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from syntara.eventstreams.exceptions import EventSubscriptionInUseError
from syntara.eventstreams.models.source import EventSubscriptionSource
from syntara.eventstreams.models.subscription import EventSubscription
from syntara.eventstreams.services.subscription_service import EventSubscriptionService
from syntara.integrations.models.integration import Integration, IntegrationType
from syntara.integrations.models.integration_configuration import KafkaConfiguration, MCPServerConfiguration
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def kafka_integration(test_db_session: AsyncSession, test_user: User) -> Integration:
    integration = Integration(
        name=f"kafka-{uuid4().hex[:8]}",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(integration_type="kafka", bootstrap_servers=["broker:9092"]),
        enabled=True,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(integration)
    await test_db_session.flush()
    return integration


@pytest_asyncio.fixture
async def runtime_credential(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> Credential:
    credential_type = CredentialType(
        name=f"kafka-conn-{uuid4().hex[:6]}",
        description="Kafka connection",
        inputs={"fields": [], "required": []},
        injectors={"extra_vars": {}, "env": {}, "file": {}},
        managed=True,
    )
    test_db_session.add(credential_type)
    await test_db_session.flush()
    credential = Credential(
        name=f"cred-{uuid4().hex[:6]}",
        credential_type_id=credential_type.id,
        project_id=test_project_id,
        created_by=test_user.id,
        enabled=True,
    )
    test_db_session.add(credential)
    await test_db_session.flush()
    return credential


@pytest_asyncio.fixture
async def workflow(test_db_session: AsyncSession, test_user: User, test_project_id: UUID) -> Workflow:
    wf = Workflow(
        name=f"wf-{uuid4().hex[:8]}",
        created_by=test_user.id,
        is_enabled=False,
        current_version=1,
        project_id=test_project_id,
    )
    test_db_session.add(wf)
    await test_db_session.flush()
    return wf


def _trigger_node(
    *,
    node_id: str,
    integration_id: UUID,
    credential_id: UUID,
    topic: str = "infra.alerts",
    input_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "topic": topic,
        "integration_id": str(integration_id),
        "credential_id": str(credential_id),
    }
    if input_schema is not None:
        parameters["input_schema"] = input_schema
    return {"id": node_id, "type": "event_subscribe_trigger", "parameters": parameters}


async def _make_version(
    session: AsyncSession,
    workflow: Workflow,
    test_user: User,
    triggers: list[dict[str, Any]],
    *,
    version: int,
) -> WorkflowVersion:
    wv = WorkflowVersion(
        workflow_id=workflow.id,
        version=version,
        schema_version="2.0.0",
        workflow_definition={
            "schema_version": "2.0.0",
            "name": workflow.name,
            "nodes": [],
            "edges": [],
            "triggers": triggers,
        },
        created_by=test_user.id,
    )
    session.add(wv)
    await session.flush()
    return wv


async def _subscriptions(session: AsyncSession, workflow_id: UUID) -> list[EventSubscription]:
    result = await session.exec(select(EventSubscription).where(col(EventSubscription.workflow_id) == workflow_id))
    return list(result.all())


async def _sources(session: AsyncSession, subscription_id: UUID) -> list[EventSubscriptionSource]:
    result = await session.exec(
        select(EventSubscriptionSource)
        .where(col(EventSubscriptionSource.subscription_id) == subscription_id)
        .order_by(col(EventSubscriptionSource.generation))
    )
    return list(result.all())


# ---------------------------------------------------------------------------
# Publication create / update / identity preservation
# ---------------------------------------------------------------------------


async def test_publish_creates_subscription_and_source(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )

    changeset = await service.sync_from_published_definition(workflow, version, enabled=True)

    assert len(changeset.created) == 1
    subscriptions = await _subscriptions(test_db_session, workflow.id)
    assert len(subscriptions) == 1
    sub = subscriptions[0]
    assert sub.desired_enabled is True
    assert sub.retired is False
    assert sub.configuration_revision == 1
    assert sub.active_source_generation == 1
    assert sub.runtime_credential_id == runtime_credential.id
    assert sub.enabled_by == test_user.id

    sources = await _sources(test_db_session, sub.id)
    assert len(sources) == 1
    source = sources[0]
    assert source.generation == 1
    assert source.integration_id == kafka_integration.id
    assert source.integration_identity == kafka_integration.id
    assert source.transport == "kafka"
    assert source.configuration.group_id == f"syntara.{source.deployment_id}.{sub.id}.1"
    assert source.retired_at is None


async def test_republish_same_source_preserves_identity_without_new_generation(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    node = _trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)
    v1 = await _make_version(test_db_session, workflow, test_user, [node], version=1)
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub_before = (await _subscriptions(test_db_session, workflow.id))[0]
    source_before = (await _sources(test_db_session, sub_before.id))[0]
    subscription_id = sub_before.id
    revision_before = sub_before.configuration_revision

    v2 = await _make_version(test_db_session, workflow, test_user, [node], version=2)
    changeset = await service.sync_from_published_definition(workflow, v2, enabled=True)

    assert len(changeset.updated) == 1
    assert len(changeset.created) == 0
    subscriptions = await _subscriptions(test_db_session, workflow.id)
    assert len(subscriptions) == 1
    sub_after = subscriptions[0]
    assert sub_after.id == subscription_id
    assert sub_after.published_version_id == v2.id  # pointer advances
    assert sub_after.configuration_revision == revision_before  # no config change
    assert sub_after.active_source_generation == 1

    sources = await _sources(test_db_session, sub_after.id)
    assert len(sources) == 1  # no new generation for unchanged source identity
    assert sources[0].id == source_before.id
    assert sources[0].configuration.group_id == source_before.configuration.group_id


async def test_configuration_change_advances_revision_same_source(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub_before = (await _subscriptions(test_db_session, workflow.id))[0]
    subscription_id = sub_before.id
    revision_before = sub_before.configuration_revision

    v2 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [
            _trigger_node(
                node_id="incoming",
                integration_id=kafka_integration.id,
                credential_id=runtime_credential.id,
                input_schema={"type": "object", "required": ["severity"]},
            )
        ],
        version=2,
    )
    await service.sync_from_published_definition(workflow, v2, enabled=True)

    sub_after = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub_after.id == subscription_id
    assert sub_after.configuration_revision == revision_before + 1
    assert sub_after.input_schema == {"type": "object", "required": ["severity"]}
    # Same source generation/group preserved through a non-source config change.
    assert sub_after.active_source_generation == 1
    assert len(await _sources(test_db_session, sub_after.id)) == 1


async def test_source_replacement_retires_old_and_allocates_new_generation(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [
            _trigger_node(
                node_id="incoming",
                integration_id=kafka_integration.id,
                credential_id=runtime_credential.id,
                topic="topic-a",
            )
        ],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub = (await _subscriptions(test_db_session, workflow.id))[0]
    subscription_id = sub.id
    revision_before = sub.configuration_revision
    gen1 = (await _sources(test_db_session, sub.id))[0]

    v2 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [
            _trigger_node(
                node_id="incoming",
                integration_id=kafka_integration.id,
                credential_id=runtime_credential.id,
                topic="topic-b",
            )
        ],
        version=2,
    )
    await service.sync_from_published_definition(workflow, v2, enabled=True)

    sub_after = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub_after.id == subscription_id  # subscription identity preserved
    assert sub_after.active_source_generation == 2
    assert sub_after.configuration_revision == revision_before + 1

    sources = await _sources(test_db_session, sub.id)
    assert len(sources) == 2  # old evidence retained, not deleted
    old, new = sources[0], sources[1]
    assert old.id == gen1.id
    assert old.retired_at is not None  # prior source retired
    assert new.generation == 2
    assert new.configuration.topic == "topic-b"
    assert new.configuration.group_id != old.configuration.group_id  # fresh group


# ---------------------------------------------------------------------------
# Unpublish / re-enable / retirement
# ---------------------------------------------------------------------------


async def test_unpublish_disables_and_retains_identity(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub_before = (await _subscriptions(test_db_session, workflow.id))[0]
    subscription_id = sub_before.id
    revision_before = sub_before.configuration_revision
    source_before = (await _sources(test_db_session, sub_before.id))[0]

    changeset = await service.sync_from_published_definition(workflow, v1, enabled=False)

    assert changeset.disabled == [subscription_id]
    sub_after = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub_after.id == subscription_id
    assert sub_after.desired_enabled is False
    assert sub_after.retired is False
    assert sub_after.configuration_revision == revision_before + 1
    # Source + group + progress retained for republish (recoverable row preserved).
    sources = await _sources(test_db_session, sub_after.id)
    assert len(sources) == 1
    assert sources[0].id == source_before.id
    assert sources[0].retired_at is None


async def test_unpublish_with_missing_version_still_disables(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    # Mirrors unpublish when the published-version record is absent: the disable
    # path is keyed by workflow and must run with version=None.
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub_before = (await _subscriptions(test_db_session, workflow.id))[0]
    source_before = (await _sources(test_db_session, sub_before.id))[0]

    changeset = await service.sync_from_published_definition(workflow, None, enabled=False)

    assert changeset.disabled == [sub_before.id]
    sub_after = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub_after.desired_enabled is False
    assert sub_after.retired is False
    # Identity/group/progress retained even without the version record.
    sources = await _sources(test_db_session, sub_after.id)
    assert len(sources) == 1
    assert sources[0].id == source_before.id
    assert sources[0].retired_at is None


async def test_republish_after_unpublish_reenables_same_identity(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    node = _trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)
    v1 = await _make_version(test_db_session, workflow, test_user, [node], version=1)
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    source_before = (await _sources(test_db_session, (await _subscriptions(test_db_session, workflow.id))[0].id))[0]
    await service.sync_from_published_definition(workflow, v1, enabled=False)

    v2 = await _make_version(test_db_session, workflow, test_user, [node], version=2)
    await service.sync_from_published_definition(workflow, v2, enabled=True)

    sub = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub.desired_enabled is True
    sources = await _sources(test_db_session, sub.id)
    assert len(sources) == 1  # no new generation; backlog/progress retained
    assert sources[0].id == source_before.id
    assert sources[0].configuration.group_id == source_before.configuration.group_id


async def test_trigger_removal_retires_subscription_and_preserves_rows(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    sub = (await _subscriptions(test_db_session, workflow.id))[0]

    v2 = await _make_version(test_db_session, workflow, test_user, [], version=2)
    changeset = await service.sync_from_published_definition(workflow, v2, enabled=True)

    assert changeset.retired == [sub.id]
    sub_after = (await _subscriptions(test_db_session, workflow.id))[0]
    assert sub_after.retired is True
    assert sub_after.desired_enabled is False
    # Evidence preserved: subscription + source rows remain, source retired not deleted.
    sources = await _sources(test_db_session, sub.id)
    assert len(sources) == 1
    assert sources[0].retired_at is not None


async def test_retired_subscription_coexists_with_new_subscription_for_same_trigger(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    node = _trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)
    v1 = await _make_version(test_db_session, workflow, test_user, [node], version=1)
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    v2 = await _make_version(test_db_session, workflow, test_user, [], version=2)
    await service.sync_from_published_definition(workflow, v2, enabled=True)  # retires it

    v3 = await _make_version(test_db_session, workflow, test_user, [node], version=3)
    await service.sync_from_published_definition(workflow, v3, enabled=True)  # recreates

    subscriptions = await _subscriptions(test_db_session, workflow.id)
    assert len(subscriptions) == 2  # one retired + one live
    live = [s for s in subscriptions if not s.retired]
    retired = [s for s in subscriptions if s.retired]
    assert len(live) == 1
    assert len(retired) == 1
    assert live[0].id != retired[0].id


# ---------------------------------------------------------------------------
# Multiple triggers / snapshots / validation
# ---------------------------------------------------------------------------


async def test_two_triggers_create_distinct_subscriptions_and_groups(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [
            _trigger_node(
                node_id="a", integration_id=kafka_integration.id, credential_id=runtime_credential.id, topic="t-a"
            ),
            _trigger_node(
                node_id="b", integration_id=kafka_integration.id, credential_id=runtime_credential.id, topic="t-b"
            ),
        ],
        version=1,
    )
    changeset = await service.sync_from_published_definition(workflow, version, enabled=True)

    assert len(changeset.created) == 2
    subscriptions = await _subscriptions(test_db_session, workflow.id)
    assert len(subscriptions) == 2
    group_ids = set()
    for sub in subscriptions:
        source = (await _sources(test_db_session, sub.id))[0]
        group_ids.add(source.configuration.group_id)
    assert len(group_ids) == 2  # distinct groups even for same integration


async def test_build_snapshot_after_unpublish_remains_discoverable(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    await service.sync_from_published_definition(workflow, v1, enabled=False)

    sub = (await _subscriptions(test_db_session, workflow.id))[0]
    snapshot = await service.build_snapshot(sub)

    assert snapshot is not None
    assert snapshot.subscription_id == sub.id
    assert snapshot.desired_enabled is False  # discoverable for downstream recovery
    assert snapshot.configuration.group_id.endswith(f".{sub.id}.1")


async def test_sync_rejects_missing_integration(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=uuid4(), credential_id=runtime_credential.id)],
        version=1,
    )

    with pytest.raises(SafeValueError):
        await service.sync_from_published_definition(workflow, version, enabled=True)


# ---------------------------------------------------------------------------
# Activation-time resource/scope checks (AC5) — applied on every enabling publish
# ---------------------------------------------------------------------------


async def test_sync_rejects_cross_project_credential(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
) -> None:
    other_project = Project(name=f"other-{uuid4().hex[:8]}", description="other")
    test_db_session.add(other_project)
    await test_db_session.flush()
    credential_type = CredentialType(
        name=f"kc-{uuid4().hex[:6]}",
        description="Kafka connection",
        inputs={"fields": [], "required": []},
        injectors={"extra_vars": {}, "env": {}, "file": {}},
        managed=True,
    )
    test_db_session.add(credential_type)
    await test_db_session.flush()
    foreign_credential = Credential(
        name=f"cred-{uuid4().hex[:6]}",
        credential_type_id=credential_type.id,
        project_id=other_project.id,
        created_by=test_user.id,
        enabled=True,
    )
    test_db_session.add(foreign_credential)
    await test_db_session.flush()

    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=foreign_credential.id)],
        version=1,
    )

    with pytest.raises(SafeValueError, match="different project"):
        await service.sync_from_published_definition(workflow, version, enabled=True)
    assert await _subscriptions(test_db_session, workflow.id) == []


async def test_sync_rejects_disabled_integration(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    runtime_credential: Credential,
) -> None:
    disabled_integration = Integration(
        name=f"kafka-{uuid4().hex[:8]}",
        integration_type=IntegrationType.KAFKA,
        configuration=KafkaConfiguration(integration_type="kafka", bootstrap_servers=["broker:9092"]),
        enabled=False,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(disabled_integration)
    await test_db_session.flush()

    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [
            _trigger_node(
                node_id="incoming", integration_id=disabled_integration.id, credential_id=runtime_credential.id
            )
        ],
        version=1,
    )

    with pytest.raises(SafeValueError, match="disabled"):
        await service.sync_from_published_definition(workflow, version, enabled=True)


async def test_sync_rejects_disabled_credential(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    test_project_id: UUID,
) -> None:
    credential_type = CredentialType(
        name=f"kc-{uuid4().hex[:6]}",
        description="Kafka connection",
        inputs={"fields": [], "required": []},
        injectors={"extra_vars": {}, "env": {}, "file": {}},
        managed=True,
    )
    test_db_session.add(credential_type)
    await test_db_session.flush()
    disabled_credential = Credential(
        name=f"cred-{uuid4().hex[:6]}",
        credential_type_id=credential_type.id,
        project_id=test_project_id,
        created_by=test_user.id,
        enabled=False,
    )
    test_db_session.add(disabled_credential)
    await test_db_session.flush()

    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=disabled_credential.id)],
        version=1,
    )

    with pytest.raises(SafeValueError, match="disabled"):
        await service.sync_from_published_definition(workflow, version, enabled=True)


async def test_sync_rejects_transport_integration_mismatch(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    runtime_credential: Credential,
) -> None:
    # A kafka-transport trigger pointing at a non-Kafka Integration must surface a
    # clean SafeValueError, not an opaque bare ValueError.
    mcp_integration = Integration(
        name=f"mcp-{uuid4().hex[:8]}",
        integration_type=IntegrationType.MCP_SERVER,
        configuration=MCPServerConfiguration(integration_type="mcp_server", base_url="https://example.com"),
        enabled=True,
        created_by=test_user.id,
        updated_by=test_user.id,
    )
    test_db_session.add(mcp_integration)
    await test_db_session.flush()

    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=mcp_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )

    with pytest.raises(SafeValueError, match="transport does not match"):
        await service.sync_from_published_definition(workflow, version, enabled=True)


# ---------------------------------------------------------------------------
# Conservative deletion guards (AC5)
# ---------------------------------------------------------------------------


async def test_deletion_guards_block_while_bound(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, version, enabled=True)

    with pytest.raises(EventSubscriptionInUseError):
        await service.assert_workflow_not_bound(workflow.id, workflow.name)
    with pytest.raises(EventSubscriptionInUseError):
        await service.assert_integration_not_bound(kafka_integration.id, kafka_integration.name)
    with pytest.raises(EventSubscriptionInUseError):
        await service.assert_credential_not_bound(runtime_credential.id, runtime_credential.name)


async def test_deletion_guards_pass_when_unbound(
    test_db_session: AsyncSession,
    test_user: User,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    # No subscriptions exist; guards must not raise.
    await service.assert_workflow_not_bound(uuid4(), "unused-workflow")
    await service.assert_integration_not_bound(uuid4(), "unused-integration")
    await service.assert_credential_not_bound(uuid4(), "unused-credential")


async def test_deletion_guard_blocks_even_after_retirement(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    v1 = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, v1, enabled=True)
    v2 = await _make_version(test_db_session, workflow, test_user, [], version=2)
    await service.sync_from_published_definition(workflow, v2, enabled=True)  # retires subscription

    # Retirement alone does not authorize deletion; the guard still blocks.
    with pytest.raises(EventSubscriptionInUseError):
        await service.assert_workflow_not_bound(workflow.id, workflow.name)


async def test_workflow_delete_restrict_fk_blocks_at_database(
    test_db_session: AsyncSession,
    test_user: User,
    workflow: Workflow,
    kafka_integration: Integration,
    runtime_credential: Credential,
) -> None:
    service = EventSubscriptionService(test_db_session, test_user)
    version = await _make_version(
        test_db_session,
        workflow,
        test_user,
        [_trigger_node(node_id="incoming", integration_id=kafka_integration.id, credential_id=runtime_credential.id)],
        version=1,
    )
    await service.sync_from_published_definition(workflow, version, enabled=True)

    # The RESTRICT FK is the DB backstop even if the app-level guard is bypassed.
    await test_db_session.delete(workflow)
    with pytest.raises(IntegrityError):
        await test_db_session.flush()
