"""Real policy evaluation guards authoring writes before any persistence or cleanup."""

from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import select

from syntara.authz.audit.authorization_denied import AuthorizationDeniedEvent
from syntara.authz.engine import clear_authz_cache
from syntara.authz.evaluator import AuthzEvaluator, evaluate_policy_input
from syntara.authz.exceptions import AuthorizationDeniedError
from syntara.authz.models import Project, Role, RoleAssignment
from syntara.core.models import User
from syntara.core.models.principal import Principal, PrincipalType, make_service_user
from syntara.projects.service import ProjectService
from syntara.workflows.exceptions import NodeKindWriteDeniedError
from syntara.workflows.models import Workflow, WorkflowVersion
from syntara.workflows.models.workflow_publish_event import PublishAction, WorkflowPublishEvent
from syntara.workflows.services.workflow_service import WorkflowService
from tests.helpers.workflow import create_minimal_workflow_definition


@pytest.fixture
def evaluator():
    return MagicMock(spec=AuthzEvaluator, evaluate=MagicMock(side_effect=evaluate_policy_input))


async def _assign_policy(db, user, project, mode, kind="script") -> None:
    if mode != "missing":
        db.add(RoleAssignment(principal_id=user.id, role_name="step-author"))
    if mode in {"global", "project", "other"}:
        deny = f"step_type:write:any:deny:{kind}"
        role = Role(name="restricted-author", policy_names=[deny])
        db.add(role)
        await db.flush()
        other = Project(name="other-project")
        db.add(other)
        await db.flush()
        db.add(
            RoleAssignment(
                principal_id=user.id,
                role_name=role.name,
                project_id=project.id if mode == "project" else other.id if mode == "other" else None,
            )
        )
    await db.commit()
    clear_authz_cache()


async def _stored_workflow(db, user, project_id, definition, *, target=None) -> tuple[Workflow, WorkflowVersion]:
    workflow = Workflow(name="governed", project_id=project_id, created_by=user.id, current_version=1)
    db.add(workflow)
    await db.flush()
    version = WorkflowVersion(
        workflow_id=workflow.id, version=1, workflow_definition=definition, schema_version="2.0.0", created_by=user.id
    )
    db.add(version)
    if target is not None:
        db.add(
            WorkflowVersion(
                workflow_id=workflow.id,
                version=2,
                workflow_definition=target,
                schema_version="2.0.0",
                created_by=user.id,
            )
        )
    await db.commit()
    return workflow, version


async def _write(service, operation, workflow, definition) -> Any:  # noqa: ANN401, PLR0911
    if operation == "save":
        return await service.update_workflow(workflow.id, name="renamed", workflow_definition=definition)
    if operation == "rename":
        return await service.update_workflow(workflow.id, name="renamed")
    if operation == "version_metadata":
        return await service.update_version_metadata(workflow.id, 1, name="release")
    if operation == "restore":
        return await service.restore_workflow_version(workflow.id, 2)
    if operation == "delete":
        return await service.delete_workflow(workflow.id)
    if operation == "inline_publish":
        return await service.publish_workflow_version(workflow.id, 1, workflow_definition=definition)
    if operation == "direct_version":
        return await service.create_workflow_version(workflow, definition, "change")
    return await ProjectService(service.session, service.user, service.opa_client).delete_project(workflow.project_id)


@pytest.mark.parametrize(
    "operation",
    ["save", "rename", "version_metadata", "restore", "delete", "inline_publish", "direct_version", "project_delete"],
)
@pytest.mark.parametrize("mode", ["allow", "global", "project", "other", "missing"])
async def test_all_write_paths(test_db_session, test_user, test_project_id, evaluator, operation, mode):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    definition = create_minimal_workflow_definition()
    workflow, version = await _stored_workflow(db, test_user, project.id, definition, target=definition)
    await _assign_policy(db, test_user, project, mode)
    service = WorkflowService(db, test_user, evaluator)
    with patch("syntara.workflows.node_permissions.AuditEventDispatcher.dispatch") as dispatch:
        if mode in {"global", "project", "missing"}:
            with pytest.raises(NodeKindWriteDeniedError) as raised:
                await _write(service, operation, workflow, definition)
            assert {b.kind for b in raised.value.blocked_step_types} >= {"script"}
            assert dispatch.called
            assert (await db.get(Workflow, workflow.id)).name == "governed"
            assert (await db.get(WorkflowVersion, version.id)).name is None
            assert (await db.get(Workflow, workflow.id)).current_version == 1
            assert (await db.get(Workflow, workflow.id)).published_version_id is None
            assert (
                await db.exec(select(WorkflowPublishEvent).where(WorkflowPublishEvent.workflow_id == workflow.id))
            ).all() == []
            await db.commit()
            await db.refresh(workflow)
            assert workflow.name == "governed"
        else:
            await _write(service, operation, workflow, definition)
            assert not any(isinstance(call.args[0], AuthorizationDeniedEvent) for call in dispatch.call_args_list)


@pytest.mark.parametrize("operation", ["save", "restore", "inline_publish", "direct_version"])
@pytest.mark.parametrize("change", ["added", "existing", "removed", "unchanged"])
async def test_checks_stored_and_submitted_types(
    test_db_session, test_user, test_project_id, evaluator, operation, change
):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    script = create_minimal_workflow_definition()
    other = create_minimal_workflow_definition(activity_type="wait")
    stored = other if change == "added" else script
    submitted = other if change == "removed" else deepcopy(script)
    if change == "existing":
        submitted["nodes"][0]["parameters"]["code"] = "print('changed')"
    workflow, _ = await _stored_workflow(db, test_user, project.id, stored, target=submitted)
    await _assign_policy(db, test_user, project, "global")
    service = WorkflowService(db, test_user, evaluator)
    with pytest.raises(NodeKindWriteDeniedError):
        await _write(service, operation, workflow, submitted)
    assert workflow.current_version == 1


@pytest.mark.parametrize("mode", ["allow", "global", "project", "other", "missing"])
@pytest.mark.parametrize("operation", ["create", "import", "duplicate"])
async def test_create_import_duplicate(test_db_session, test_user, test_project_id, evaluator, mode, operation):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    await _assign_policy(db, test_user, project, mode)
    service = WorkflowService(db, test_user, evaluator)

    async def create() -> Any:  # noqa: ANN401
        return await service.create_workflow(
            name="new",
            description=None,
            labels={},
            workflow_definition=create_minimal_workflow_definition(),
            project_id=project.id,
            is_import=operation == "import",
        )

    if mode in {"global", "project", "missing"}:
        with pytest.raises(NodeKindWriteDeniedError):
            await create()
        assert (await db.exec(select(Workflow).where(Workflow.name == "new"))).first() is None
    else:
        workflow, _, _ = await create()
        assert workflow.name == "new"


async def test_published_version_blocks_draft_and_pointer_changes_atomically(
    test_db_session, test_user, test_project_id, evaluator
):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    script = create_minimal_workflow_definition()
    draft = create_minimal_workflow_definition(activity_type="wait")
    workflow, published = await _stored_workflow(db, test_user, project.id, script, target=draft)
    workflow.current_version = 2
    workflow.published_version_id = published.id
    workflow.is_enabled = True
    db.add(
        WorkflowPublishEvent(
            workflow_id=workflow.id,
            version_id=published.id,
            action=PublishAction.PUBLISHED,
            actor_id=test_user.id,
        )
    )
    await db.commit()
    await _assign_policy(db, test_user, project, "global")
    service = WorkflowService(db, test_user, evaluator)
    with pytest.raises(NodeKindWriteDeniedError):
        await service.update_workflow(workflow.id, name="renamed", workflow_definition=draft)
    with pytest.raises(NodeKindWriteDeniedError):
        await service.unpublish_workflow(workflow.id)
    with pytest.raises(NodeKindWriteDeniedError):
        await service.publish_workflow_version(workflow.id, 2)
    await db.refresh(workflow)
    assert workflow.name == "governed"
    assert workflow.current_version == 2
    assert workflow.published_version_id == published.id
    assert workflow.is_enabled
    assert (
        len((await db.exec(select(WorkflowPublishEvent).where(WorkflowPublishEvent.workflow_id == workflow.id))).all())
        == 1
    )


async def test_published_only_denial_blocks_project_delete(test_db_session, test_user, test_project_id, evaluator):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    allowed_draft = create_minimal_workflow_definition(activity_type="wait")
    denied_published = create_minimal_workflow_definition()
    workflow, _ = await _stored_workflow(db, test_user, project.id, allowed_draft, target=denied_published)
    published = (
        await db.exec(
            select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == 2)
        )
    ).one()
    workflow.current_version = 1
    workflow.published_version_id = published.id
    workflow.is_enabled = True
    await db.commit()
    await _assign_policy(db, test_user, project, "global")
    with pytest.raises(NodeKindWriteDeniedError):
        await ProjectService(db, test_user, evaluator).delete_project(project.id)
    assert await db.get(Project, project.id) is not None


async def test_step_type_summary_includes_latest_and_published_versions(
    test_db_session, test_user, test_project_id, evaluator
):
    db = test_db_session
    draft = create_minimal_workflow_definition(activity_type="wait")
    published_definition = create_minimal_workflow_definition(activity_type="script")
    workflow, _ = await _stored_workflow(db, test_user, test_project_id, draft, target=published_definition)
    published = (
        await db.exec(
            select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == 2)
        )
    ).one()
    workflow.published_version_id = published.id
    workflow.is_enabled = True
    await db.commit()

    summary = await WorkflowService(db, test_user, evaluator).to_read(workflow)

    assert summary.step_types == ["manual_trigger", "script", "wait"]


async def test_missing_current_version_returns_unavailable_step_type_summary(
    test_db_session, test_user, test_project_id, evaluator
):
    workflow, _ = await _stored_workflow(
        test_db_session, test_user, test_project_id, create_minimal_workflow_definition()
    )
    workflow.current_version = 99
    await test_db_session.commit()

    summary = await WorkflowService(test_db_session, test_user, evaluator).to_read(workflow)

    assert summary.step_types is None


async def test_empty_current_definition_returns_empty_step_type_summary(
    test_db_session, test_user, test_project_id, evaluator
):
    workflow, _ = await _stored_workflow(
        test_db_session,
        test_user,
        test_project_id,
        {"triggers": [], "nodes": []},
    )

    summary = await WorkflowService(test_db_session, test_user, evaluator).to_read(workflow)

    assert summary.step_types == []


async def test_selected_historical_definition_is_checked(test_db_session, test_user, test_project_id, evaluator):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    script = create_minimal_workflow_definition()
    permitted_draft = create_minimal_workflow_definition(activity_type="wait")
    workflow, _ = await _stored_workflow(db, test_user, project.id, script, target=permitted_draft)
    workflow.current_version = 2
    await db.commit()
    await _assign_policy(db, test_user, project, "global")

    with pytest.raises(NodeKindWriteDeniedError):
        await WorkflowService(db, test_user, evaluator).update_version_metadata(workflow.id, 1, name="release")

    version_id = (
        await db.exec(
            select(WorkflowVersion.id).where(
                WorkflowVersion.workflow_id == workflow.id,
                WorkflowVersion.version == 1,
            )
        )
    ).one()
    assert (await db.get(WorkflowVersion, version_id)).name is None


async def test_inline_publish_checks_the_selected_version_definition(
    test_db_session, test_user, test_project_id, evaluator
):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    permitted = create_minimal_workflow_definition(activity_type="wait")
    selected_denied = create_minimal_workflow_definition()
    workflow, _ = await _stored_workflow(db, test_user, project.id, permitted, target=selected_denied)
    await _assign_policy(db, test_user, project, "global")

    with pytest.raises(NodeKindWriteDeniedError):
        await WorkflowService(db, test_user, evaluator).publish_workflow_version(
            workflow.id,
            2,
            workflow_definition=permitted,
        )

    assert workflow.current_version == 1
    assert workflow.published_version_id is None


async def test_reports_multiple_blocked_step_types(test_db_session, test_user, test_project_id, evaluator):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    db.add(RoleAssignment(principal_id=test_user.id, role_name="step-author"))
    deny_role = Role(
        name="restricted-author-multiple-kinds",
        policy_names=[
            "step_type:write:any:deny:script",
            "step_type:write:any:deny:wait",
        ],
    )
    db.add(deny_role)
    await db.flush()
    db.add(RoleAssignment(principal_id=test_user.id, role_name=deny_role.name))
    await db.commit()
    clear_authz_cache()

    definition = create_minimal_workflow_definition()
    definition["nodes"].append({"id": "wait-2", "type": "wait", "parameters": {"duration": 5}})
    with pytest.raises(NodeKindWriteDeniedError) as raised:
        await WorkflowService(db, test_user, evaluator).create_workflow(
            name="multiple-denials",
            description=None,
            labels={},
            workflow_definition=definition,
            project_id=project.id,
        )

    assert {blocked.kind for blocked in raised.value.blocked_step_types} >= {"script", "wait"}


async def test_project_denial_precedes_external_cleanup(test_db_session, test_user, test_project_id, evaluator):
    db = test_db_session
    project = await db.get(Project, test_project_id)
    await _stored_workflow(db, test_user, project.id, create_minimal_workflow_definition())
    await _assign_policy(db, test_user, project, "global")
    service = ProjectService(db, test_user, evaluator)
    with (
        patch.object(service, "_cleanup_temporal_schedules") as schedules,
        patch.object(service, "_cleanup_file_storage") as files,
        pytest.raises(NodeKindWriteDeniedError),
    ):
        await service.delete_project(project.id)
    schedules.assert_not_called()
    files.assert_not_called()
    assert await db.get(Project, project.id) is not None


@pytest.mark.parametrize("available", [False, True])
async def test_unavailable_evaluation_leaves_metadata_unchanged(
    test_db_session, test_user, test_project_id, evaluator, available
):
    workflow, _ = await _stored_workflow(
        test_db_session, test_user, test_project_id, create_minimal_workflow_definition()
    )
    if available:
        evaluator.evaluate.side_effect = RuntimeError("evaluation failed")
    service = WorkflowService(test_db_session, test_user, evaluator if available else None)
    with pytest.raises(AuthorizationDeniedError, match="unavailable"):
        await service.update_workflow(workflow.id, name="must-not-save")
    await test_db_session.commit()
    await test_db_session.refresh(workflow)
    assert workflow.name == "governed"


async def test_builtin_seeder_exemption_does_not_exempt_normal_saves(
    test_db_session, test_user, test_project_id, evaluator
):
    from syntara.workflows.seed_builtin import _seed_one

    project = await test_db_session.get(Project, test_project_id)
    await _assign_policy(test_db_session, test_user, project, "global")
    definition = create_minimal_workflow_definition()
    with patch("syntara.workflows.seed_builtin._sync_builtin_schedules"):
        await _seed_one(test_db_session, definition, test_user.id, project.id)
    builtins = (await test_db_session.exec(select(Workflow).where(Workflow.is_builtin == True))).all()  # noqa: E712
    assert len(builtins) == 1
    service = WorkflowService(test_db_session, test_user, evaluator)
    with pytest.raises(NodeKindWriteDeniedError):
        await service.create_workflow(
            name="custom", description=None, labels={}, workflow_definition=definition, project_id=project.id
        )


async def test_certificate_caller_is_checked_after_route_permission_bypass(
    test_db_session, test_user, test_project_id, evaluator
):
    from fastapi import FastAPI, Request
    from httpx import ASGITransport, AsyncClient

    from syntara.core.database.session import get_db
    from syntara.core.exception_registry import register_exceptions
    from syntara.workflows.router import get_authz_evaluator, router

    db = test_db_session
    service_user = make_service_user("worker.ao.svc")
    db.add(Principal.for_service("worker.ao.svc"))
    await db.commit()
    project = await db.get(Project, test_project_id)
    await _assign_policy(db, service_user, project, "global")
    app = FastAPI()
    app.state.authz_evaluator = evaluator

    async def verified_certificate(request: Request, call_next) -> Any:  # noqa: ANN401
        request.state.is_cert_authenticated = True
        request.state.cert_cn = "worker.ao.svc"
        return await call_next(request)

    app.middleware("http")(verified_certificate)

    async def database() -> AsyncGenerator[Any, None]:
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_authz_evaluator] = lambda: evaluator
    app.include_router(router, prefix="/api/v1")
    register_exceptions(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post(
            "/api/v1/workflows",
            json={
                "name": "cert-denied",
                "project_id": str(project.id),
                "workflow_definition": create_minimal_workflow_definition(),
            },
        )
    assert response.status_code == 403
    assert response.json()["code"] == "NODE_KIND_WRITE_DENIED"
    assert response.json()["blocked_step_types"][0]["kind"] == "script"
    assert "policy" not in response.json()["blocked_step_types"][0]


async def test_service_account_is_subject_to_the_same_denies(test_db_session, test_project_id, evaluator):
    db = test_db_session
    principal_id = uuid4()
    db.add(Principal(id=principal_id, principal_type=PrincipalType.SERVICE_ACCOUNT))
    await db.commit()
    user = User(id=principal_id, username="automation")
    object.__setattr__(user, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)
    project = await db.get(Project, test_project_id)
    await _assign_policy(db, user, project, "project")
    service = WorkflowService(db, user, evaluator)
    with (
        patch("syntara.workflows.node_permissions.AuditEventDispatcher.dispatch") as dispatch,
        pytest.raises(NodeKindWriteDeniedError),
    ):
        await service.create_workflow(
            name="sa-denied",
            description=None,
            labels={},
            workflow_definition=create_minimal_workflow_definition(),
            project_id=project.id,
        )
    event = dispatch.call_args.args[0]
    assert event.principal_type == PrincipalType.SERVICE_ACCOUNT


async def test_project_delete_prevents_new_workflows_from_bypassing_checks(
    test_db_session, test_db_session_factory, test_user, test_project_id, evaluator
):
    await test_db_session.commit()
    service = ProjectService(test_db_session, test_user, evaluator)

    async def try_concurrent_insert(*_args: object) -> None:
        async with test_db_session_factory() as concurrent:
            await concurrent.exec(text("SET LOCAL lock_timeout = '100ms'"))
            concurrent.add(Workflow(name="concurrent", project_id=test_project_id, created_by=test_user.id))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await concurrent.flush()
            await concurrent.rollback()

    with patch.object(service, "_check_workflow_step_types", side_effect=try_concurrent_insert) as check:
        await service.delete_project(test_project_id)
    check.assert_awaited_once()
