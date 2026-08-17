"""Integration tests for authorization hardening.

Covers privilege escalation prevention (SEC-001 to SEC-005),
role boundary enforcement (SEC-020, SEC-021), cross-project
isolation (SEC-024 to SEC-027), and group membership edge cases
(SEC-028 to SEC-031).
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import insert
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project, RoleAssignment
from syntara.core.models import User
from syntara.core.models.group import Group, user_groups
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_project_admin,
    make_project_user,
    make_user_role,
)

# ============================================================================
# SEC-001 to SEC-005: Privilege Escalation Prevention
# ============================================================================


class TestPrivilegeEscalation:
    """Verify users cannot escalate their own privileges."""

    @pytest.mark.asyncio
    async def test_user_cannot_self_assign_admin_role(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-001: Regular user cannot assign admin role to themselves."""
        limited_user = await user_factory(username="limited-sec1", email="limited-sec1@test.com")
        await make_user_role(test_db_session, limited_user)
        auth_as(limited_user)

        resp = await auth_client.post(
            "/api/v1/role_assignments",
            json={"principal_id": str(limited_user.id), "role_name": "admin"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_user_cannot_assign_role_via_can_i(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-001b: can-i confirms role-assignment:assign is denied for regular user."""
        limited_user = await user_factory(username="limited-sec1b", email="limited-sec1b@test.com")
        await make_user_role(test_db_session, limited_user)
        auth_as(limited_user)

        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "assign", "resource_type": "role-assignment"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_project_admin_cannot_create_global_policies(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-003: Project-admin cannot create global policies."""
        admin = await user_factory(username="admin-sec3", email="admin-sec3@test.com")
        proj_admin = await user_factory(username="projadm-sec3", email="projadm-sec3@test.com")
        await make_admin(test_db_session, admin)

        # Admin creates project, assign proj_admin as project-admin
        auth_as(admin)
        resp = await auth_client.post("/api/v1/projects", json={"name": "sec3-proj"})
        assert resp.status_code == 201

        project = (await test_db_session.exec(select(Project).where(Project.name == "sec3-proj"))).first()
        assert project is not None
        await make_project_admin(test_db_session, proj_admin, project)

        # Project-admin tries to create a global policy
        auth_as(proj_admin)
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "create", "resource_type": "policy"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_auditor_cannot_modify_resources(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-004: Auditor cannot perform any write actions."""
        auditor = await user_factory(username="aud-sec4", email="aud-sec4@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        write_actions = [
            ("create", "workflow"),
            ("update", "workflow"),
            ("delete", "workflow"),
            ("create", "policy"),
            ("delete", "policy"),
            ("run", "execution"),
        ]
        for action, resource_type in write_actions:
            resp = await auth_client.post(
                "/api/v1/authz/can_i",
                json={"action": action, "resource_type": resource_type},
            )
            assert resp.status_code == 200
            assert resp.json()["allowed"] is False, f"Auditor should not be allowed {resource_type}:{action}"

    @pytest.mark.asyncio
    async def test_user_role_cannot_read_other_users(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-005: User role no longer grants user:read:any — only directory lookups."""
        user_a = await user_factory(username="usera-sec5", email="usera-sec5@test.com", group_names=["users"])
        user_b = await user_factory(username="userb-sec5", email="userb-sec5@test.com")

        auth_as(user_a)

        # Can read self (via authenticated role's user:read:self)
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "user", "resource_id": str(user_a.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

        # Cannot read other users (user:read:any removed from user role)
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "user", "resource_id": str(user_b.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False


# ============================================================================
# SEC-020, SEC-021: Role Boundary Enforcement
# ============================================================================


class TestRoleBoundaries:
    """Verify role permissions are exactly as expected via what-can-i."""

    @pytest.mark.asyncio
    async def test_user_role_expected_permissions(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-020: User role grants exactly the expected permissions."""
        user = await user_factory(username="user-sec20", email="user-sec20@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        # limit=100 to fetch all permissions in one page; pagination is tested separately in WI-5.
        resp = await auth_client.post("/api/v1/authz/what_can_i", json={"limit": 100})
        assert resp.status_code == 200
        permissions = resp.json()["resources"]

        # Filter to system-scoped (scope=any) allow permissions only
        system_perms = [p for p in permissions if p["effect"] == "allow" and p["scope"] == "any"]
        system_actions: set[str] = set()
        for p in system_perms:
            system_actions.update(p["actions"])

        # User role should grant project:create, directory lookups at system scope
        for expected in ["project:create", "user-directory:read", "group-directory:read"]:
            assert expected in system_actions, f"User role missing {expected}"

        # User role should NOT grant workflow CRUD, execution, or policy management at system scope
        for forbidden in [
            "workflow:create",
            "workflow:read",
            "workflow:delete",
            "execution:run",
            "credential:read",
            "policy:create",
            "policy:delete",
            "role:create",
            "role:delete",
        ]:
            assert forbidden not in system_actions, f"User role unexpectedly grants {forbidden}"

    @pytest.mark.asyncio
    async def test_auditor_strictly_read_only(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-021: Auditor role is strictly read-only."""
        auditor = await user_factory(username="aud-sec21", email="aud-sec21@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        # limit=100 to fetch all permissions in one page; pagination is tested separately in WI-5.
        resp = await auth_client.post("/api/v1/authz/what_can_i", json={"limit": 100})
        assert resp.status_code == 200
        permissions = resp.json()["resources"]

        # Filter to auditor-role-specific policies:
        # - scope=any (exclude project-scoped policies from authenticated group)
        # - Exclude authenticated + user role policies (granted via authenticated group)
        non_auditor_policy_names = {
            "user:read:self",
            "user:update:self",
            "role-assignment:read:self",
            "user_identity:read:self",
            "user_identity:detach:self",
            "project:create:any",
            "user-directory:read:any",
            "group-directory:read:any",
        }
        auditor_allows = [
            p
            for p in permissions
            if p["effect"] == "allow" and p["scope"] == "any" and p["policy_name"] not in non_auditor_policy_names
        ]
        auditor_actions: set[str] = set()
        for p in auditor_allows:
            auditor_actions.update(p["actions"])

        assert len(auditor_actions) > 0, "Auditor should have at least one permission"

        # All auditor-specific actions should be read-only
        read_only_verbs = {"read", "read-all"}
        for action_str in auditor_actions:
            action_verb = action_str.rsplit(":", 1)[-1]
            assert action_verb in read_only_verbs, f"Auditor has non-read action: {action_str}"


# ============================================================================
# SEC-024 to SEC-027: Cross-Project Isolation
# ============================================================================


class TestCrossProjectIsolation:
    """Verify project-level isolation cannot be bypassed."""

    @pytest.mark.asyncio
    async def test_project_admin_cannot_manage_other_project(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-024/025: Project-admin of A cannot delete or manage project B."""
        admin = await user_factory(username="admin-sec24", email="admin-sec24@test.com")
        proj_admin = await user_factory(username="padm-sec24", email="padm-sec24@test.com")
        await make_admin(test_db_session, admin)

        auth_as(admin)
        resp = await auth_client.post("/api/v1/projects", json={"name": "sec24-a"})
        assert resp.status_code == 201
        proj_a_name = resp.json()["name"]

        resp = await auth_client.post("/api/v1/projects", json={"name": "sec24-b"})
        assert resp.status_code == 201
        proj_b_name = resp.json()["name"]

        proj_a = (await test_db_session.exec(select(Project).where(Project.name == proj_a_name))).first()
        assert proj_a is not None
        await make_project_admin(test_db_session, proj_admin, proj_a)

        auth_as(proj_admin)

        # Can delete in own project
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "delete", "resource_type": "workflow", "resource_project": proj_a_name},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

        # Cannot delete in other project
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "delete", "resource_type": "workflow", "resource_project": proj_b_name},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_user_with_two_projects_isolated_from_third(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-026: User with project-user in A and B has no access to C."""
        admin = await user_factory(username="admin-sec26", email="admin-sec26@test.com")
        multi_user = await user_factory(username="multi-sec26", email="multi-sec26@test.com")
        await make_admin(test_db_session, admin)

        auth_as(admin)
        projects = {}
        for name in ("sec26-a", "sec26-b", "sec26-c"):
            resp = await auth_client.post("/api/v1/projects", json={"name": name})
            assert resp.status_code == 201
            proj = (await test_db_session.exec(select(Project).where(Project.name == name))).first()
            assert proj is not None
            projects[name] = proj

        # Assign multi_user to A and B only
        await make_project_user(test_db_session, multi_user, projects["sec26-a"])
        await make_project_user(test_db_session, multi_user, projects["sec26-b"])

        auth_as(multi_user)

        # Can access A and B
        for proj_name in ("sec26-a", "sec26-b"):
            resp = await auth_client.post(
                "/api/v1/authz/can_i",
                json={"action": "read", "resource_type": "workflow", "resource_project": proj_name},
            )
            assert resp.status_code == 200
            assert resp.json()["allowed"] is True, f"Should have access to {proj_name}"

        # Cannot access C
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "workflow", "resource_project": "sec26-c"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False


# ============================================================================
# SEC-028 to SEC-031: Group Membership Edge Cases
# ============================================================================


class TestGroupMembershipEdgeCases:
    """Verify edge cases in group-based authorization."""

    @pytest.mark.asyncio
    async def test_user_with_no_groups_gets_authenticated_policies(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-028: User with no custom groups still gets authenticated group policies."""
        lonely = await user_factory(username="lonely-sec28", email="lonely-sec28@test.com")
        auth_as(lonely)

        # limit=100 to fetch all permissions in one page; pagination is tested separately in WI-5.
        resp = await auth_client.post("/api/v1/authz/what_can_i", json={"limit": 100})
        assert resp.status_code == 200
        permissions = resp.json()["resources"]

        # Should have only the authenticated role policies (not user role)
        policy_names = {p["policy_name"] for p in permissions}
        assert "user:read:self" in policy_names
        assert "project:create:any" not in policy_names

    @pytest.mark.asyncio
    async def test_group_with_no_role_grants_nothing_extra(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-029: Group without any role assignments grants no extra permissions."""
        user = await user_factory(username="norole-sec29", email="norole-sec29@test.com")

        # Create empty group (no role assignments)
        empty_group = Group(name=f"empty-sec29-{uuid4()}", description="", labels={})
        test_db_session.add(empty_group)
        await test_db_session.flush()
        await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=empty_group.id))
        await test_db_session.commit()

        auth_as(user)

        # workflow:create should be denied (only authenticated policies, no user role)
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "create", "resource_type": "workflow"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_removing_group_role_revokes_access(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-031: Removing a role assignment from a group revokes access for all members."""
        user = await user_factory(username="revoke-sec31", email="revoke-sec31@test.com")

        group = Group(name=f"revoke-sec31-{uuid4()}", description="", labels={})
        test_db_session.add(group)
        await test_db_session.flush()
        role_assignment = RoleAssignment(group_id=group.id, role_name="auditor")
        test_db_session.add(role_assignment)
        await test_db_session.exec(insert(user_groups).values(user_id=user.id, group_id=group.id))
        await test_db_session.commit()

        auth_as(user)

        # Allowed while role assignment exists (auditor has policy:read)
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "policy"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

        # Remove role assignment from group
        await test_db_session.delete(role_assignment)
        await test_db_session.commit()

        # Now denied
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "policy"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False


# ============================================================================
# SEC-046: PermissionChecker 403 Detail
# ============================================================================


class TestPermissionChecker403:
    """Verify PermissionChecker returns informative 403 details."""

    @pytest.mark.asyncio
    async def test_403_includes_resource_and_action(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """SEC-046: 403 response includes resource_type and action in detail."""
        auditor = await user_factory(username="aud-sec46", email="aud-sec46@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        # Auditor tries to create a policy (requires admin)
        resp = await auth_client.post(
            "/api/v1/policies",
            json={
                "name": "sneaky-policy",
                "description": "test",
                "statements": [{"effect": "allow", "actions": ["workflow:read"], "scope": "any"}],
            },
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "policy" in detail
        assert "create" in detail

    @pytest.mark.asyncio
    async def test_403_on_role_assignment_attempt(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Non-admin trying to assign a role gets 403 with details."""
        limited_user = await user_factory(username="limited-sec46b", email="limited-sec46b@test.com")
        await make_user_role(test_db_session, limited_user)
        auth_as(limited_user)

        resp = await auth_client.post(
            "/api/v1/role_assignments",
            json={"principal_id": str(limited_user.id), "role_name": "admin"},
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "role-assignment" in detail
        assert "assign" in detail
