"""Independent identities: management, directory limits, and deny precedence."""

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models.assignments import RoleAssignment
from syntara.authz.models.policy import Policy
from syntara.authz.models.role import Role
from syntara.core.models import User

BASE = "/api/v1/service_accounts"


@pytest.mark.asyncio
async def test_authenticated_creation_and_read_with_admin_only_management(
    base_client: AsyncClient,
    admin_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    owner = await user_factory(username="identity-owner", email="identity-owner@example.com")
    stranger = await user_factory(username="identity-stranger", email="identity-stranger@example.com")
    auth_as(owner)
    created = await base_client.post(BASE, json={"name": "shared-automation"})
    assert created.status_code == 201, created.text
    account = created.json()
    account_id = account["id"]
    assert "project_id" not in account
    assert "project_name" not in account
    assert (
        await test_db_session.exec(select(RoleAssignment).where(RoleAssignment.principal_id == UUID(account_id)))
    ).all() == []
    credential = await admin_client.post(
        f"{BASE}/{account_id}/credentials", json={"credential_type": "client_credentials"}
    )
    assert credential.status_code == 201, credential.text
    credential_id = credential.json()["id"]
    assert credential.json()["client_secret"]
    listing = await base_client.get(BASE, params={"include_total": True})
    assert listing.status_code == 200, listing.text
    assert account_id in {row["id"] for row in listing.json()["resources"]}
    assert (await base_client.get(BASE, params={"project_id": "removed"})).status_code == 422
    assert (await base_client.get(f"{BASE}/{account_id}")).status_code == 200
    assert (await base_client.get(f"{BASE}/{account_id}/credentials")).status_code == 200
    assert (await base_client.get(f"{BASE}/{account_id}/credentials/{credential_id}")).status_code == 200

    for action in ("read", "create", "update", "delete", "rotate_secret", "disable", "enable"):
        check = await base_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": action,
                "resource_type": "service_account",
                "resource_id": account_id,
                "resource_metadata": {"created_by": str(owner.id)},
            },
        )
        assert check.status_code == 200
        assert check.json()["allowed"] is (action in {"read", "create"})

    assert (await base_client.patch(f"{BASE}/{account_id}", json={"description": "denied"})).status_code == 403
    assert (await base_client.delete(f"{BASE}/{account_id}")).status_code == 403
    for action in ("disable", "enable"):
        assert (await base_client.post(f"{BASE}/{account_id}/{action}")).status_code == 403
        assert (await base_client.post(f"{BASE}/{account_id}/credentials/{credential_id}/{action}")).status_code == 403
    assert (
        await base_client.post(f"{BASE}/{account_id}/credentials", json={"credential_type": "client_credentials"})
    ).status_code == 403
    assert (
        await base_client.post(f"{BASE}/{account_id}/credentials/{credential_id}/rotate", json={})
    ).status_code == 403
    assert (await base_client.delete(f"{BASE}/{account_id}/credentials/{credential_id}")).status_code == 403

    auth_as(stranger)
    directory = await base_client.get(f"{BASE}/directory", params={"name[contains]": "shared", "limit": 1})
    assert directory.status_code == 200, directory.text
    assert directory.json()["resources"] == [{"id": account_id, "name": "shared-automation", "status": "active"}]
    assert account_id in {row["id"] for row in (await base_client.get(BASE)).json()["resources"]}
    assert (await base_client.get(f"{BASE}/{account_id}")).status_code == 200
    assert (await base_client.patch(f"{BASE}/{account_id}", json={"name": "stolen"})).status_code == 403
    assert (await base_client.delete(f"{BASE}/{account_id}")).status_code == 403
    for action in ("disable", "enable"):
        assert (await base_client.post(f"{BASE}/{account_id}/{action}")).status_code == 403
        assert (await base_client.post(f"{BASE}/{account_id}/credentials/{credential_id}/{action}")).status_code == 403
    assert (await base_client.get(f"{BASE}/{account_id}/credentials")).status_code == 200
    assert (await base_client.get(f"{BASE}/{account_id}/credentials/{credential_id}")).status_code == 200
    assert (
        await base_client.post(f"{BASE}/{account_id}/credentials", json={"credential_type": "client_credentials"})
    ).status_code == 403
    assert (
        await base_client.post(f"{BASE}/{account_id}/credentials/{credential_id}/rotate", json={})
    ).status_code == 403
    assert (await base_client.delete(f"{BASE}/{account_id}/credentials/{credential_id}")).status_code == 403
    assert (await admin_client.delete(f"{BASE}/{account_id}")).status_code == 204


@pytest.mark.asyncio
async def test_system_auditor_and_explicit_creator_deny(
    base_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    owner = await user_factory(username="deny-owner", email="deny-owner@example.com")
    auditor = await user_factory(username="identity-auditor", email="identity-auditor@example.com")
    auth_as(owner)
    created = await base_client.post(BASE, json={"name": "audit-identity"})
    assert created.status_code == 201
    account_id = created.json()["id"]
    test_db_session.add(RoleAssignment(principal_id=auditor.id, role_name="auditor"))
    test_db_session.add(
        Policy(
            name="deny-own-identity",
            statements=[
                {
                    "effect": "deny",
                    "actions": ["service_account:*"],
                    "scope": "any",
                    "conditions": {"resource_metadata": {"created_by": str(owner.id)}},
                }
            ],
        )
    )
    test_db_session.add(Role(name="identity-denial", policy_names=["deny-own-identity"]))
    test_db_session.add(RoleAssignment(principal_id=owner.id, role_name="identity-denial"))
    await test_db_session.commit()
    assert (await base_client.get(BASE, params={"include_total": True})).json()["total"] == 0
    assert (await base_client.patch(f"{BASE}/{account_id}", json={"description": "denied"})).status_code == 403
    auth_as(auditor)
    assert (await base_client.get(f"{BASE}/{account_id}")).status_code == 200
    assert (await base_client.get(f"{BASE}/{account_id}/credentials")).status_code == 200
    assert (
        await base_client.post(f"{BASE}/{account_id}/credentials", json={"credential_type": "client_credentials"})
    ).status_code == 403
    assert (await base_client.delete(f"{BASE}/{account_id}")).status_code == 403


@pytest.mark.asyncio
async def test_directory_pagination_and_shared_trigger_bindings(
    base_client: AsyncClient,
    test_db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    auth_as: Callable[[User], None],
) -> None:
    from uuid import uuid4

    from syntara.authz.models.project import Project
    from syntara.service_accounts.models.service_account import ServiceAccount
    from syntara.workflows.exceptions import TriggerValidationError, WebhookServiceAccountNotAuthorizedError
    from syntara.workflows.models.workflow import Workflow
    from syntara.workflows.services.webhook_trigger_service import WebhookTriggerService
    from syntara.workflows.validators.workflow_integrations import validate_workflow_references

    owner = await user_factory(username="shared-owner", email="shared-owner@example.com")
    auth_as(owner)
    accounts = []
    for index in range(3):
        response = await base_client.post(BASE, json={"name": f"directory-page-{index}"})
        assert response.status_code == 201
        accounts.append(response.json())
    selector = await user_factory(username="shared-selector", email="shared-selector@example.com")
    auth_as(selector)
    params: dict[str, str | int | bool] = {
        "name[contains]": "directory-page",
        "limit": 2,
        "include_total": True,
        "sort": "name",
    }
    first = (await base_client.get(f"{BASE}/directory", params=params)).json()
    assert first["total"] == 3
    assert len(first["resources"]) == 2
    second = (await base_client.get(f"{BASE}/directory", params={**params, "cursor": first["next"]})).json()
    assert [row["id"] for row in [*first["resources"], *second["resources"]]] == [row["id"] for row in accounts]
    assert all(set(row) == {"id", "name", "status"} for row in first["resources"])

    account_id = UUID(accounts[0]["id"])
    account = await test_db_session.get(ServiceAccount, account_id)
    assert account is not None
    service = WebhookTriggerService(test_db_session, owner)
    for trigger_type in ("webhook_trigger", "eda_trigger"):
        project = Project(name=f"shared-{trigger_type}")
        test_db_session.add(project)
        await test_db_session.flush()
        workflow = Workflow(name=f"shared-{trigger_type}", project_id=project.id, created_by=owner.id)
        test_db_session.add(workflow)
        await test_db_session.flush()
        definition = {
            "triggers": [
                {
                    "id": "trigger",
                    "type": trigger_type,
                    "parameters": {
                        "webhook_path": f"shared-{trigger_type}",
                        "authorized_service_account_ids": [str(account_id)],
                    },
                }
            ]
        }
        assert await validate_workflow_references(test_db_session, definition, project.id, is_import=True) == []
        triggers = await service.sync_webhook_triggers(workflow.id, definition, trigger_type=trigger_type)
        assert len(triggers) == 1
        await service.verify_service_account_authorization(triggers[0].id, account_id)
        with pytest.raises(WebhookServiceAccountNotAuthorizedError):
            await service.verify_service_account_authorization(triggers[0].id, UUID(accounts[1]["id"]))
        with pytest.raises(TriggerValidationError, match="not found"):
            await service._sync_trigger_sa_bindings(triggers[0].id, {uuid4()})
    assert (
        await test_db_session.exec(select(RoleAssignment).where(RoleAssignment.principal_id == account_id))
    ).all() == []
