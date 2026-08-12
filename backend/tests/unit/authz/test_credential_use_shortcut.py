"""Unit tests for the credential:use visibility Python shortcut.

Tests _derive_allowed_projects and _extract_credential_ids — pure functions
with no DB or Rego dependency.
"""

from typing import Any

import pytest

from syntara.authz.engine import _derive_allowed_projects
from syntara.workflows.services.workflow_service import WorkflowService


def _allow(actions: list[str], scope: str = "any", project: str = "", **kwargs: object) -> dict[str, Any]:
    p: dict[str, Any] = {"effect": "allow", "actions": actions, "scope": scope, "name": "test"}
    if project:
        p["project"] = project
    p.update(kwargs)
    return p


def _deny(actions: list[str], scope: str = "any") -> dict[str, Any]:
    return {"effect": "deny", "actions": actions, "scope": scope, "name": "test"}


class TestDeriveUseAllowedProjects:  # noqa: D101
    def test_empty_policies_returns_empty_list(self) -> None:
        assert _derive_allowed_projects([], "credential", "use") == ([], False)

    def test_admin_system_scope_any_returns_unrestricted(self) -> None:
        policies = [_allow(["credential:use"], scope="any")]
        result = _derive_allowed_projects(policies, "credential", "use")
        assert result == ([], True)

    def test_admin_system_scope_system_returns_unrestricted(self) -> None:
        policies = [_allow(["credential:use"], scope="system")]
        assert _derive_allowed_projects(policies, "credential", "use") == ([], True)

    def test_project_user_project_scope_returns_project(self) -> None:
        policies = [_allow(["credential:use"], scope="project", project="proj-a")]
        assert _derive_allowed_projects(policies, "credential", "use") == (["proj-a"], False)

    def test_multiple_project_scoped_grants(self) -> None:
        policies = [
            _allow(["credential:use"], scope="project", project="proj-a"),
            _allow(["credential:use"], scope="project", project="proj-b"),
        ]
        result = _derive_allowed_projects(policies, "credential", "use")
        assert result is not None
        names, unrestricted = result
        assert set(names) == {"proj-a", "proj-b"}
        assert not unrestricted

    def test_project_auditor_no_use_policy_returns_empty(self) -> None:
        policies = [_allow(["credential:read"], scope="project", project="proj-a")]
        assert _derive_allowed_projects(policies, "credential", "use") == ([], False)

    def test_deny_policy_returns_none(self) -> None:
        policies = [_deny(["credential:use"])]
        assert _derive_allowed_projects(policies, "credential", "use") is None

    def test_deny_with_allow_returns_none(self) -> None:
        policies = [
            _allow(["credential:use"], scope="project", project="proj-a"),
            _deny(["credential:use"]),
        ]
        assert _derive_allowed_projects(policies, "credential", "use") is None

    def test_conditions_present_returns_none(self) -> None:
        policies = [_allow(["credential:use"], scope="project", project="proj-a", conditions={"key": "val"})]
        assert _derive_allowed_projects(policies, "credential", "use") is None

    def test_wildcard_action_credential_star_counts(self) -> None:
        policies = [_allow(["credential:*"], scope="project", project="proj-a")]
        assert _derive_allowed_projects(policies, "credential", "use") == (["proj-a"], False)

    def test_wildcard_action_at_system_scope_returns_unrestricted(self) -> None:
        policies = [_allow(["credential:*"], scope="any")]
        assert _derive_allowed_projects(policies, "credential", "use") == ([], True)

    def test_unrelated_deny_does_not_block(self) -> None:
        policies = [
            _allow(["credential:use"], scope="project", project="proj-a"),
            _deny(["workflow:create"]),  # different resource — should not block
        ]
        assert _derive_allowed_projects(policies, "credential", "use") == (["proj-a"], False)

    def test_deny_other_credential_action_does_not_block(self) -> None:
        policies = [
            _allow(["credential:use"], scope="project", project="proj-a"),
            _deny(["credential:delete"]),  # deny on different action
        ]
        assert _derive_allowed_projects(policies, "credential", "use") == (["proj-a"], False)

    def test_mixed_read_and_use_policies(self) -> None:
        """Read policies don't affect the use shortcut result."""
        policies = [
            _allow(["credential:read"], scope="project", project="proj-a"),
            _allow(["credential:use"], scope="project", project="proj-b"),
        ]
        result = _derive_allowed_projects(policies, "credential", "use")
        assert result == (["proj-b"], False)

    @pytest.mark.parametrize("scope", ["any", "system", ""])
    def test_various_system_scope_values_return_unrestricted(self, scope: str) -> None:
        policies = [_allow(["credential:use"], scope=scope)]
        result = _derive_allowed_projects(policies, "credential", "use")
        assert result == ([], True)

    def test_project_scope_without_project_name_skipped(self) -> None:
        """Project-scoped policy with no project name is skipped (no append)."""
        policies = [_allow(["credential:use"], scope="project", project="")]
        assert _derive_allowed_projects(policies, "credential", "use") == ([], False)

    def test_non_allow_non_deny_effect_skipped(self) -> None:
        """Policies with unknown effect values are skipped."""
        policies = [{"effect": "conditional", "actions": ["credential:use"], "scope": "any", "name": "test"}]
        assert _derive_allowed_projects(policies, "credential", "use") == ([], False)


class TestExtractCredentialIds:
    """Tests for WorkflowService._extract_credential_ids (pure static method)."""

    def _wf(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return {"nodes": nodes}

    def test_empty_nodes_returns_empty(self) -> None:
        assert WorkflowService._extract_credential_ids(self._wf([])) == set()

    def test_no_nodes_key_returns_empty(self) -> None:
        assert WorkflowService._extract_credential_ids({}) == set()

    def test_single_credential_id(self) -> None:
        wf = self._wf([{"id": "n1", "parameters": {"credential_id": "cred-1"}}])
        assert WorkflowService._extract_credential_ids(wf) == {"cred-1"}

    def test_multiple_nodes_with_credentials(self) -> None:
        wf = self._wf(
            [
                {"id": "n1", "parameters": {"credential_id": "cred-1"}},
                {"id": "n2", "parameters": {"credential_id": "cred-2"}},
            ]
        )
        assert WorkflowService._extract_credential_ids(wf) == {"cred-1", "cred-2"}

    def test_integration_connections_credential_ids(self) -> None:
        """Task Agent nodes store credentials inside integration_connections."""
        wf = self._wf(
            [
                {
                    "id": "n1",
                    "parameters": {
                        "integration_connections": [
                            {"credential_id": "conn-cred-1"},
                            {"credential_id": "conn-cred-2"},
                            {"other_field": "no-cred"},
                        ]
                    },
                }
            ]
        )
        assert WorkflowService._extract_credential_ids(wf) == {"conn-cred-1", "conn-cred-2"}

    def test_mixed_credential_id_and_integration_connections(self) -> None:
        wf = self._wf(
            [
                {
                    "id": "n1",
                    "parameters": {
                        "credential_id": "direct-cred",
                        "integration_connections": [{"credential_id": "conn-cred"}],
                    },
                }
            ]
        )
        assert WorkflowService._extract_credential_ids(wf) == {"direct-cred", "conn-cred"}

    def test_node_without_parameters_skipped(self) -> None:
        wf = self._wf([{"id": "n1"}])
        assert WorkflowService._extract_credential_ids(wf) == set()

    def test_deduplicates_same_credential_across_nodes(self) -> None:
        wf = self._wf(
            [
                {"id": "n1", "parameters": {"credential_id": "cred-x"}},
                {"id": "n2", "parameters": {"credential_id": "cred-x"}},
            ]
        )
        assert WorkflowService._extract_credential_ids(wf) == {"cred-x"}
