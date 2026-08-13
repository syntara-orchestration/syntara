"""Unit tests for script permission registration in BUILTIN_POLICIES."""
import pytest

from syntara.authz.role_conventions import BUILTIN_POLICIES, builtin_role_policy_names


class TestScriptPermissions:
    def test_script_edit_system_scope_exists(self) -> None:
        names = {p.name for p in BUILTIN_POLICIES}
        assert "script:edit:any" in names

    def test_script_execute_system_scope_exists(self) -> None:
        names = {p.name for p in BUILTIN_POLICIES}
        assert "script:execute:any" in names

    def test_script_edit_project_scope_exists(self) -> None:
        names = {p.name for p in BUILTIN_POLICIES}
        assert "script:edit:project" in names

    def test_script_execute_project_scope_exists(self) -> None:
        names = {p.name for p in BUILTIN_POLICIES}
        assert "script:execute:project" in names

    def test_admin_has_script_edit(self) -> None:
        policies = builtin_role_policy_names("admin")
        assert "script:edit:any" in policies

    def test_admin_has_script_execute(self) -> None:
        policies = builtin_role_policy_names("admin")
        assert "script:execute:any" in policies

    def test_project_admin_has_script_edit(self) -> None:
        policies = builtin_role_policy_names("project-admin")
        assert "script:edit:project" in policies

    def test_project_admin_has_script_execute(self) -> None:
        policies = builtin_role_policy_names("project-admin")
        assert "script:execute:project" in policies

    def test_project_user_has_script_execute(self) -> None:
        policies = builtin_role_policy_names("project-user")
        assert "script:execute:project" in policies

    def test_project_user_does_not_have_script_edit(self) -> None:
        policies = builtin_role_policy_names("project-user")
        assert "script:edit:project" not in policies
