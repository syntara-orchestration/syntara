"""Rego evaluation tests for ``workflow_node`` permissions (ANSTRAT-1750).

Node kinds are not a new Rego concept.  A node check is an ordinary
``workflow_node:<action>`` evaluation with the node kind carried as the
``kind`` resource label, so these tests prove the *existing* engine gives
the intended verdicts:

- the ``authenticated`` builtin allow grants every kind by default
- a deny matched on the ``kind`` label wins over that allow
- a project-scoped deny applies only in its project
- a deny on a role every principal holds is system-wide, admins included
- ``denied_by`` names the policy so the execution record can cite it
"""

from typing import Any

from tests.unit.authz.conftest import allow_policy, build_opa_input, deny_policy, policies_for_role


def _node_input(
    action: str,
    kind: str,
    *,
    project: str = "",
    policies: list[dict[str, Any]],
) -> dict[str, Any]:
    return build_opa_input(
        action=action,
        resource_type="workflow_node",
        resource_project=project,
        resource_labels={"kind": kind},
        effective_policies=policies,
    )


def _http_deny(name: str = "deny-http-execute", scope: str = "any", project: str = "") -> dict[str, Any]:
    policy = deny_policy(
        name,
        ["workflow_node:execute"],
        scope=scope,
        conditions={"resource_labels": {"kind": "http_request"}},
    )
    if project:
        policy["project"] = project
    return policy


class TestDefaultAllow:
    """F-22: every authenticated principal may use every kind unless denied."""

    def test_authenticated_may_execute_any_kind(self, opa_evaluate):
        for kind in ("http_request", "script", "agentic", "aap_job_template"):
            result = opa_evaluate(_node_input("execute", kind, policies=policies_for_role("authenticated")))
            assert result["allow"] is True, kind

    def test_authenticated_may_write_any_kind(self, opa_evaluate):
        result = opa_evaluate(_node_input("write", "webhook_trigger", policies=policies_for_role("authenticated")))
        assert result["allow"] is True

    def test_no_policies_means_no_access(self, opa_evaluate):
        result = opa_evaluate(_node_input("execute", "http_request", policies=[]))
        assert result["allow"] is False
        assert result["deny"] is False


class TestDenyByKind:
    """A deny matched on the kind label overrides the default allow."""

    def test_denied_kind_is_denied(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), _http_deny()]
        result = opa_evaluate(_node_input("execute", "http_request", policies=policies))
        assert result["allow"] is False
        assert result["deny"] is True
        assert result["denied_by"] == "deny-http-execute"
        assert result["denial_reason"] == "policy_deny"

    def test_other_kind_still_allowed(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), _http_deny()]
        result = opa_evaluate(_node_input("execute", "script", policies=policies))
        assert result["allow"] is True

    def test_other_action_on_denied_kind_still_allowed(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), _http_deny()]
        result = opa_evaluate(_node_input("write", "http_request", policies=policies))
        assert result["allow"] is True

    def test_deny_without_kind_condition_denies_every_kind(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), deny_policy("deny-all-execute", ["workflow_node:execute"])]
        for kind in ("http_request", "script"):
            result = opa_evaluate(_node_input("execute", kind, policies=policies))
            assert result["allow"] is False, kind

    def test_wildcard_deny_covers_write_and_execute(self, opa_evaluate):
        policies = [
            *policies_for_role("authenticated"),
            deny_policy("deny-http-all", ["workflow_node:*"], conditions={"resource_labels": {"kind": "http_request"}}),
        ]
        for action in ("write", "execute"):
            result = opa_evaluate(_node_input(action, "http_request", policies=policies))
            assert result["allow"] is False, action


class TestProjectScopedDeny:
    """F-5: the project on a deny comes from the role assignment, not the statement."""

    def test_deny_applies_in_its_project(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), _http_deny(scope="project", project="proj-a")]
        result = opa_evaluate(_node_input("execute", "http_request", project="proj-a", policies=policies))
        assert result["allow"] is False

    def test_deny_does_not_apply_in_other_project(self, opa_evaluate):
        policies = [*policies_for_role("authenticated"), _http_deny(scope="project", project="proj-a")]
        result = opa_evaluate(_node_input("execute", "http_request", project="proj-b", policies=policies))
        assert result["allow"] is True


class TestDenyIsSystemWide:
    """F-12: a deny denies anyone, admins included; there is no superuser."""

    def test_admin_with_authenticated_deny_is_denied(self, opa_evaluate):
        policies = [*policies_for_role("admin"), *policies_for_role("authenticated"), _http_deny()]
        result = opa_evaluate(_node_input("execute", "http_request", policies=policies))
        assert result["allow"] is False
        assert result["denied_by"] == "deny-http-execute"

    def test_admin_without_deny_is_allowed(self, opa_evaluate):
        policies = [*policies_for_role("admin"), *policies_for_role("authenticated")]
        result = opa_evaluate(_node_input("execute", "http_request", policies=policies))
        assert result["allow"] is True

    def test_explicit_allow_cannot_beat_deny(self, opa_evaluate):
        policies = [
            allow_policy(
                "allow-http", ["workflow_node:execute"], conditions={"resource_labels": {"kind": "http_request"}}
            ),
            _http_deny(),
        ]
        result = opa_evaluate(_node_input("execute", "http_request", policies=policies))
        assert result["allow"] is False
