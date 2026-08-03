"""Group 1: RBAC Basics — core role-based access control checks."""

import pytest

from tests.unit.authz.conftest import build_authz_input, policies_for_role


class TestAdminFullAccess:
    """Admin role grants access to all resource types."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("create", "policy"),
            ("delete", "workflow"),
            ("read", "workflow"),
            ("create", "project"),
            ("run", "execution"),
            ("read", "execution"),
            ("delete", "project"),
        ],
        ids=[
            "policy:create",
            "workflow:delete",
            "workflow:read",
            "project:create",
            "execution:run",
            "execution:read",
            "project:delete",
        ],
    )
    def test_admin_full_access(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("admin"),
            )
        )
        assert result["allow"] is True


class TestUserRole:
    """User role grants project:create, directory lookups only."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("create", "project"),
            ("read", "user-directory"),
            ("read", "group-directory"),
        ],
        ids=[
            "project:create",
            "user-directory:read",
            "group-directory:read",
        ],
    )
    def test_user_role_allowed_actions(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("user"),
            )
        )
        assert result["allow"] is True

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("create", "policy"),
            ("delete", "policy"),
            ("create", "workflow"),
            ("read", "workflow"),
            ("run", "execution"),
            ("read", "credential"),
            ("read", "user"),
            ("read", "group"),
        ],
        ids=[
            "policy:create",
            "policy:delete",
            "workflow:create",
            "workflow:read",
            "execution:run",
            "credential:read",
            "user:read",
            "group:read",
        ],
    )
    def test_user_role_denied_actions(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("user"),
            )
        )
        assert result["allow"] is False


class TestAuditorRole:
    """Auditor role grants read-only access."""

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("read", "workflow"),
            ("read", "execution"),
            ("read", "policy"),
            ("read", "role"),
            ("read", "setting"),
        ],
        ids=[
            "workflow:read",
            "execution:read",
            "policy:read",
            "role:read",
            "setting:read",
        ],
    )
    def test_auditor_read_allowed(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("auditor"),
            )
        )
        assert result["allow"] is True

    @pytest.mark.parametrize(
        ("action", "resource_type"),
        [
            ("create", "workflow"),
            ("update", "workflow"),
            ("delete", "workflow"),
            ("create", "policy"),
            ("run", "execution"),
            ("write", "setting"),
        ],
        ids=[
            "workflow:create",
            "workflow:update",
            "workflow:delete",
            "policy:create",
            "execution:run",
            "setting:write",
        ],
    )
    def test_auditor_write_denied(self, evaluate_policy, action: str, resource_type: str):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("auditor"),
            )
        )
        assert result["allow"] is False


class TestRoleBoundaries:
    """Cross-role boundary checks."""

    def test_user_cannot_read_other_users(self, evaluate_policy):
        """User role no longer has user:read:any — reading another user is denied."""
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id="other-user-id",
                user_id="test-user-id",
                effective_policies=policies_for_role("user"),
            )
        )
        assert result["allow"] is False


class TestAuthenticatedRole:
    """Authenticated role grants default permissions to all authenticated users."""

    @pytest.mark.parametrize(
        ("action", "resource_type", "expected"),
        [
            ("create", "project", False),
            ("read", "workflow", False),
            ("create", "workflow", False),
            ("create", "policy", False),
        ],
        ids=[
            "project:create-denied",
            "workflow:read-denied",
            "workflow:create-denied",
            "policy:create-denied",
        ],
    )
    def test_authenticated_role_permissions(
        self,
        evaluate_policy,
        action: str,
        resource_type: str,
        expected: bool,  # noqa: FBT001
    ):
        result = evaluate_policy(
            build_authz_input(
                action=action,
                resource_type=resource_type,
                effective_policies=policies_for_role("authenticated"),
            )
        )
        assert result["allow"] is expected

    def test_authenticated_role_self_read(self, evaluate_policy):
        """Authenticated role allows user:read when resource_id matches user_id (self scope)."""
        user_id = "self-user-uuid"
        result = evaluate_policy(
            build_authz_input(
                action="read",
                resource_type="user",
                resource_id=user_id,
                user_id=user_id,
                effective_policies=policies_for_role("authenticated"),
            )
        )
        assert result["allow"] is True

    def test_authenticated_role_self_update(self, evaluate_policy):
        """Authenticated role allows user:update when resource_id matches user_id (self scope)."""
        user_id = "self-user-uuid"
        result = evaluate_policy(
            build_authz_input(
                action="update",
                resource_type="user",
                resource_id=user_id,
                user_id=user_id,
                effective_policies=policies_for_role("authenticated"),
            )
        )
        assert result["allow"] is True
