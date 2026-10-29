"""The execute permission applies to each node's kind, labels, and project."""

import pytest

from tests.unit.authz.conftest import allow_policy, build_opa_input, deny_policy, policies_for_role


class TestDefaultExecutePermission:
    """Authenticated principals can execute nodes until a policy denies them."""

    def test_authenticated_user_can_execute_a_node_without_a_deny(self, opa_evaluate) -> None:
        result = opa_evaluate(
            build_opa_input(
                action="execute",
                resource_type="workflow_node",
                resource_labels={"kind": "script", "language": "python"},
                effective_policies=policies_for_role("authenticated"),
            )
        )

        assert result["allow"] is True


class TestTargetedExecuteDeny:
    """A deny applies to matching node attributes in its assigned scope."""

    @pytest.mark.parametrize(
        ("labels", "allowed"),
        [
            ({"kind": "script", "language": "python"}, False),
            ({"kind": "script", "language": "bash"}, True),
            ({"kind": "http_request", "method": "POST"}, True),
        ],
        ids=["matching-node", "other-language", "other-kind"],
    )
    def test_deny_matches_only_the_selected_node_attributes(
        self,
        opa_evaluate,
        labels,
        allowed: bool,  # noqa: FBT001
    ) -> None:
        policies = [
            allow_policy("node-execute-default", ["workflow_node:execute"]),
            deny_policy(
                "deny-python-script",
                ["workflow_node:execute"],
                conditions={"resource_labels": {"kind": "script", "language": "python"}},
            ),
        ]

        result = opa_evaluate(
            build_opa_input(
                action="execute",
                resource_type="workflow_node",
                resource_labels=labels,
                effective_policies=policies,
            )
        )

        assert result["allow"] is allowed
        assert result["denied_by"] == ("deny-python-script" if not allowed else "")

    @pytest.mark.parametrize(
        ("project", "allowed"),
        [("restricted", False), ("other", True)],
        ids=["assigned-project", "other-project"],
    )
    def test_project_scoped_deny_matches_only_its_project(
        self,
        opa_evaluate,
        project: str,
        allowed: bool,  # noqa: FBT001
    ) -> None:
        project_deny = deny_policy(
            "deny-project-http",
            ["workflow_node:execute"],
            scope="project",
            conditions={"resource_labels": {"kind": "http_request"}},
        )
        project_deny["project"] = "restricted"  # Injected by the role-assignment resolver.

        result = opa_evaluate(
            build_opa_input(
                action="execute",
                resource_type="workflow_node",
                resource_project=project,
                resource_labels={"kind": "http_request"},
                effective_policies=[allow_policy("node-execute-default", ["workflow_node:execute"]), project_deny],
            )
        )

        assert result["allow"] is allowed

    def test_node_deny_does_not_revoke_workflow_execute(self, opa_evaluate) -> None:
        result = opa_evaluate(
            build_opa_input(
                action="execute",
                resource_type="workflow",
                effective_policies=[
                    allow_policy("workflow-execute", ["workflow:execute"]),
                    deny_policy(
                        "deny-script",
                        ["workflow_node:execute"],
                        conditions={"resource_labels": {"kind": "script"}},
                    ),
                ],
            )
        )

        assert result["allow"] is True
