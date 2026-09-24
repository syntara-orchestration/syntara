"""Integration tests for the save-time ``workflow_node:write`` check (ANSTRAT-1750).

Exercises the real Rego evaluator against a real database: a deny policy on
node kind ``http_request`` is attached to a custom role and assigned to the
test user, then every workflow save path is driven through ``WorkflowService``.

The rule under test is "write = introduce": a kind already present in the
latest saved version of the workflow stays editable, only kinds the save adds
are evaluated.
"""

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.evaluator import RegoEvaluator
from syntara.authz.models import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.authz.seed import seed_authz_data
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from syntara.workflows.exceptions import NodeKindWriteDeniedError, WorkflowDefinitionInvalidError
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.validation_finding import (
    ValidationCategory,
    ValidationResult,
    ValidationSeverity,
)
from syntara.workflows.node_kind_switch import DISABLED_NODE_KINDS_SETTING_KEY
from syntara.workflows.services.workflow_service import WorkflowService
from tests.fixtures.settings import FakeSettingsCache

_PATCH_VALIDATOR = "syntara.workflows.services.workflow_service.workflow_validator"
_PATCH_WEBHOOK_SVC = "syntara.workflows.services.workflow_service.WebhookTriggerService"

_DENIED_KIND = "http_request"
_ALLOWED_KIND = "script"


def _mock_validator_valid() -> MagicMock:
    """Return a workflow_validator stand-in whose findings always pass."""
    mock = MagicMock()
    mock.collect_findings.return_value = ValidationResult(is_valid=True, error_count=0, warning_count=0, findings=[])
    return mock


def _mock_webhook_service() -> MagicMock:
    """Return a WebhookTriggerService stand-in with an async sync method."""
    svc = MagicMock()
    svc.return_value.sync_webhook_triggers = AsyncMock(return_value=[])
    return svc


def _definition(*kinds: str) -> dict[str, Any]:
    """Build a workflow definition with one node per entry in *kinds*."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = [{"from": "trigger_manual", "to": "node_0"}]
    for index, kind in enumerate(kinds):
        node_id = f"node_{index}"
        nodes.append({"id": node_id, "name": f"Node {index}", "type": kind, "parameters": {}})
        if index:
            edges.append({"from": f"node_{index - 1}", "to": node_id})
    return {
        "schema_version": "2.0.0",
        "name": "node-kind-test",
        "description": "Node kind permission test",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger", "parameters": {}}],
        "nodes": nodes,
        "edges": edges,
    }


@pytest.fixture
async def real_authz_evaluator() -> AsyncGenerator[RegoEvaluator, None]:
    """Provide the real in-process Rego evaluator."""
    evaluator = RegoEvaluator()
    evaluator.start()
    assert await evaluator.health() is True
    yield evaluator
    await evaluator.stop()


@pytest.fixture(autouse=True)
def runtime_settings() -> Generator[FakeSettingsCache, None, None]:
    """Install the SettingsCache singleton the save paths read defaults from."""
    import syntara.settings.cache.settings_cache as settings_module

    cache = FakeSettingsCache()
    original = settings_module._runtime_settings
    settings_module._runtime_settings = cache  # type: ignore[assignment]
    try:
        yield cache
    finally:
        settings_module._runtime_settings = original


@pytest.fixture(autouse=True)
async def _seed_authz(test_db_session: AsyncSession) -> None:
    """Seed built-in policies, roles and groups (grants workflow_node:write:any)."""
    await seed_authz_data(test_db_session)


async def _deny_node_kind_write(session: AsyncSession, user: User, kind: str) -> None:
    """Attach a deny policy for ``workflow_node:write`` on *kind* to *user*."""
    policy_name = f"deny-node-write-{kind}"
    role_name = f"deny-node-write-role-{kind}"
    session.add(
        Policy(
            id=uuid4(),
            name=policy_name,
            description=f"Deny introducing {kind} nodes",
            statements=[
                {
                    "effect": "deny",
                    "actions": ["workflow_node:write"],
                    "scope": "any",
                    "conditions": {"resource_labels": {"kind": kind}},
                }
            ],
            is_builtin=False,
            labels={},
        )
    )
    session.add(
        Role(
            id=uuid4(),
            name=role_name,
            description=f"Role denying {kind} nodes",
            is_builtin=False,
            policy_names=[policy_name],
            labels={},
        )
    )
    group = Group(name=f"deny-node-grp-{uuid4()}", description="", labels={})
    session.add(group)
    await session.flush()
    session.add(RoleAssignment(group_id=group.id, role_name=role_name))
    await session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
    await session.commit()


async def _create_workflow(
    service: WorkflowService,
    project_id: UUID,
    name: str,
    definition: dict[str, Any],
) -> Workflow:
    """Create a workflow with validation stubbed out."""
    with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
        workflow, _version, _result = await service.create_workflow(
            name=name,
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=project_id,
        )
    return workflow


class TestSaveTimeNodeKindWrite:
    """Save paths reject only the kinds a save introduces."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_allowed_user_can_create_workflow_with_any_kind(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """Without a deny policy the builtin authenticated allow covers every kind."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)

        workflow = await _create_workflow(
            service, test_project_id, "allowed-create", _definition(_DENIED_KIND, _ALLOWED_KIND)
        )

        assert workflow.id is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_new_workflow_with_denied_kind_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """A brand-new workflow has an empty baseline, so the denied kind is introduced."""
        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)

        with pytest.raises(NodeKindWriteDeniedError) as exc_info:
            await _create_workflow(service, test_project_id, "denied-create", _definition(_ALLOWED_KIND, _DENIED_KIND))

        denied_kinds = [denial.kind for denial in exc_info.value.denials]
        assert denied_kinds == [_DENIED_KIND]
        assert exc_info.value.denials[0].denied_by == f"deny-node-write-{_DENIED_KIND}"

        rows = await test_db_session.exec(select(Workflow).where(Workflow.name == "denied-create"))
        assert rows.first() is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_other_kinds_unaffected_by_deny(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """A deny on one kind leaves every other kind usable."""
        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)

        workflow = await _create_workflow(service, test_project_id, "other-kinds", _definition(_ALLOWED_KIND))

        assert workflow.id is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_editing_existing_workflow_keeps_denied_kind_editable(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """The denied kind is already in the baseline, so the edit is allowed."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(
            service, test_project_id, "pre-existing", _definition(_DENIED_KIND, _ALLOWED_KIND)
        )

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        edited = _definition(_DENIED_KIND, _ALLOWED_KIND)
        edited["nodes"][0]["name"] = "Renamed"
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            version, _result = await service.create_workflow_version(workflow, edited, "rename")

        assert version is not None
        assert version.version == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_second_node_of_denied_kind_is_allowed(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """Presence, not count, is the test — a second node of the kind introduces nothing."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "second-node", _definition(_DENIED_KIND))

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            version, _result = await service.create_workflow_version(
                workflow, _definition(_DENIED_KIND, _DENIED_KIND), "add another"
            )

        assert version is not None
        assert version.version == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_adding_new_denied_kind_to_existing_workflow_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """A kind absent from the baseline is introduced even on an existing workflow."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "add-denied", _definition(_ALLOWED_KIND))

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            pytest.raises(NodeKindWriteDeniedError) as exc_info,
        ):
            await service.create_workflow_version(workflow, _definition(_ALLOWED_KIND, _DENIED_KIND), "add http")

        assert [denial.kind for denial in exc_info.value.denials] == [_DENIED_KIND]

        versions = await test_db_session.exec(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id))
        assert len(list(versions.all())) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publish_with_inline_definition_rejects_denied_kind(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """Atomic save-and-publish is a save path and uses the pre-save baseline."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "publish-denied", _definition(_ALLOWED_KIND))

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()),
            pytest.raises(NodeKindWriteDeniedError),
        ):
            await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
                workflow_definition=_definition(_ALLOWED_KIND, _DENIED_KIND),
            )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_restore_reintroducing_denied_kind_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """Restoring an old version that carries the denied kind re-introduces it."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "restore-denied", _definition(_DENIED_KIND))

        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            version_2, _result = await service.create_workflow_version(
                workflow, _definition(_ALLOWED_KIND), "drop http"
            )
        assert version_2 is not None

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        with pytest.raises(NodeKindWriteDeniedError) as exc_info:
            await service.restore_workflow_version(workflow.id, 1)

        assert [denial.kind for denial in exc_info.value.denials] == [_DENIED_KIND]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_restore_without_new_kinds_is_allowed(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """A restore whose kinds are all in the baseline is unaffected by the deny."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(
            service, test_project_id, "restore-allowed", _definition(_DENIED_KIND, _ALLOWED_KIND)
        )

        renamed = _definition(_DENIED_KIND, _ALLOWED_KIND)
        renamed["nodes"][0]["name"] = "Renamed"
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            version_2, _result = await service.create_workflow_version(workflow, renamed, "rename")
        assert version_2 is not None

        await _deny_node_kind_write(test_db_session, test_user, _DENIED_KIND)

        _workflow, restored = await service.restore_workflow_version(workflow.id, 1)

        assert restored.version == 3


class TestPublishedBy:
    """Publish records the publishing principal on the version."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_publish_sets_published_by(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """publish_workflow_version stamps published_by with the caller."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "published-by", _definition(_ALLOWED_KIND))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()),
        ):
            _workflow, version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
            )

        assert version.published_by == test_user.id

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unpublish_leaves_published_by(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
    ) -> None:
        """Unpublishing does not clear published_by — triggered runs may be re-armed."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "unpublish-by", _definition(_ALLOWED_KIND))

        with (
            patch(_PATCH_VALIDATOR, _mock_validator_valid()),
            patch(_PATCH_WEBHOOK_SVC, _mock_webhook_service()),
        ):
            _workflow, version, _warning = await service.publish_workflow_version(
                workflow_id=workflow.id,
                version=1,
            )
            await service.unpublish_workflow(workflow.id)

        refreshed = await test_db_session.get(WorkflowVersion, version.id)
        assert refreshed is not None
        assert refreshed.published_by == test_user.id


class TestDisabledNodeKindsAtSaveTime:
    """The platform-wide kill switch blocks saves that still carry a disabled kind."""

    @staticmethod
    def _disable(runtime_settings: FakeSettingsCache, *kinds: str) -> None:
        """Set the ``workflows.disabled_node_kinds`` runtime setting."""
        runtime_settings._store[DISABLED_NODE_KINDS_SETTING_KEY] = list(kinds)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_with_disabled_kind_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
        runtime_settings: FakeSettingsCache,
    ) -> None:
        """A new workflow containing a disabled kind cannot be saved."""
        self._disable(runtime_settings, _DENIED_KIND)
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)

        with pytest.raises(WorkflowDefinitionInvalidError) as exc_info:
            await service.create_workflow(
                name="kill-switch-create",
                description=None,
                labels={},
                workflow_definition=_definition(_DENIED_KIND),
                project_id=test_project_id,
            )

        findings = exc_info.value.validation_result.findings
        assert any(
            finding.category == ValidationCategory.node_kind_disabled and finding.severity == ValidationSeverity.error
            for finding in findings
        )

        rows = await test_db_session.exec(select(Workflow).where(Workflow.name == "kill-switch-create"))
        assert rows.first() is None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_adding_disabled_kind_to_existing_workflow_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
        runtime_settings: FakeSettingsCache,
    ) -> None:
        """Saving a new version that introduces a disabled kind is refused."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "kill-switch-add", _definition(_ALLOWED_KIND))

        self._disable(runtime_settings, _DENIED_KIND)

        with pytest.raises(WorkflowDefinitionInvalidError):
            await service.create_workflow_version(
                workflow, _definition(_ALLOWED_KIND, _DENIED_KIND), "add disabled kind"
            )

        versions = await test_db_session.exec(select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id))
        assert len(list(versions.all())) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_removing_disabled_kind_succeeds_with_warning(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
        runtime_settings: FakeSettingsCache,
    ) -> None:
        """A save that drops the last disabled node is allowed and records a warning."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(
            service, test_project_id, "kill-switch-remove", _definition(_DENIED_KIND, _ALLOWED_KIND)
        )

        self._disable(runtime_settings, _DENIED_KIND)

        version, result = await service.create_workflow_version(
            workflow, _definition(_ALLOWED_KIND), "drop disabled kind"
        )

        assert version is not None
        assert version.version == 2
        assert any(
            finding.category == ValidationCategory.node_kind_disabled and finding.severity == ValidationSeverity.warning
            for finding in result.findings
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_restore_of_version_with_disabled_kind_is_rejected(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_project_id: UUID,
        real_authz_evaluator: RegoEvaluator,
        runtime_settings: FakeSettingsCache,
    ) -> None:
        """A disabled kind cannot come back through a restore."""
        service = WorkflowService(test_db_session, test_user, real_authz_evaluator)
        workflow = await _create_workflow(service, test_project_id, "kill-switch-restore", _definition(_DENIED_KIND))
        with patch(_PATCH_VALIDATOR, _mock_validator_valid()):
            version_2, _result = await service.create_workflow_version(workflow, _definition(_ALLOWED_KIND), "drop it")
        assert version_2 is not None

        self._disable(runtime_settings, _DENIED_KIND)

        with pytest.raises(WorkflowDefinitionInvalidError):
            await service.restore_workflow_version(workflow.id, 1)
