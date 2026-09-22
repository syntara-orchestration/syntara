"""Unit tests for launch-time node-kind checks (ANSTRAT-1750, slice 4).

Covers the kill-switch pre-flight, the denied-set computation (with a stubbed
evaluator and against the real Rego policy), run-principal resolution and the
``permission_check`` edge rule.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from syntara.authz.evaluator import evaluate_policy_input
from syntara.workflows.exceptions import NodeKindDisabledError
from syntara.workflows.node_launch_checks import (
    check_node_kinds_enabled,
    compute_denied_nodes,
    get_node_authz_evaluator,
    load_principal_authz_context,
    resolve_run_principal,
    set_node_authz_evaluator,
    validate_permission_check_edges,
)
from syntara.workflows.node_permissions import NodeKindDenial
from tests.unit.authz.conftest import deny_policy, policies_for_role

PRINCIPAL_ID = UUID("11111111-1111-4111-8111-111111111111")
PUBLISHER_ID = UUID("22222222-2222-4222-8222-222222222222")


def _definition() -> dict[str, Any]:
    """Definition with two script nodes, an http_request node and flow control."""
    return {
        "schema_version": "2.0.0",
        "name": "wf",
        "triggers": [{"id": "trigger", "type": "manual_trigger", "parameters": {}}],
        "nodes": [
            {"id": "script_a", "type": "script", "parameters": {}},
            {"id": "script_b", "type": "script", "parameters": {}},
            {"id": "call", "type": "http_request", "parameters": {}},
            {"id": "gate", "type": "condition", "parameters": {}},
        ],
        "edges": [],
    }


def _result(value: object | None) -> Any:  # noqa: ANN401
    """Wrap a value in an object exposing ``.first()`` like a query result."""
    res = MagicMock()
    res.first.return_value = value
    return res


def _db_stub(*, user: object | None = None, service_account: object | None = None, project_name: str = "proj") -> Any:  # noqa: ANN401
    """Async session stub answering the project-name and principal lookups by table."""
    db = MagicMock()

    async def _exec(statement: Any) -> Any:  # noqa: ANN401
        text = str(statement).lower()
        if "projects" in text:
            return _result(project_name)
        if "service_accounts" in text:
            return _result(service_account)
        return _result(user)

    db.exec = AsyncMock(side_effect=_exec)
    return db


class TestKillSwitchPreflight:
    """check_node_kinds_enabled refuses a definition containing a disabled kind."""

    @pytest.mark.asyncio
    async def test_passes_when_nothing_disabled(self) -> None:
        with patch(
            "syntara.workflows.node_launch_checks.get_disabled_node_kinds",
            AsyncMock(return_value=frozenset()),
        ):
            await check_node_kinds_enabled(_definition())

    @pytest.mark.asyncio
    async def test_raises_listing_offending_nodes(self) -> None:
        with (
            patch(
                "syntara.workflows.node_launch_checks.get_disabled_node_kinds",
                AsyncMock(return_value=frozenset({"script"})),
            ),
            pytest.raises(NodeKindDisabledError) as exc_info,
        ):
            await check_node_kinds_enabled(_definition())

        assert exc_info.value.disabled_nodes == [
            {"node_id": "script_a", "kind": "script"},
            {"node_id": "script_b", "kind": "script"},
        ]
        assert "script_a" in str(exc_info.value)


class TestRunPrincipal:
    """Triggered runs (scheduled, webhook, EDA) act as the publisher; interactive runs as the caller."""

    @pytest.mark.parametrize("trigger_type", ["manual_trigger", None])
    def test_interactive_triggers_use_invoker(self, trigger_type: str | None) -> None:
        version = MagicMock(published_by=PUBLISHER_ID, created_by=uuid4())
        assert resolve_run_principal(version, invoker_id=PRINCIPAL_ID, trigger_type=trigger_type) == PRINCIPAL_ID

    @pytest.mark.parametrize("trigger_type", ["scheduled_trigger", "webhook_trigger", "eda_trigger"])
    def test_unattended_triggers_use_publisher(self, trigger_type: str) -> None:
        version = MagicMock(published_by=PUBLISHER_ID, created_by=uuid4())
        assert resolve_run_principal(version, invoker_id=PRINCIPAL_ID, trigger_type=trigger_type) == PUBLISHER_ID

    def test_falls_back_to_version_author_when_never_published(self) -> None:
        author = uuid4()
        version = MagicMock(published_by=None, created_by=author)
        assert resolve_run_principal(version, invoker_id=PRINCIPAL_ID, trigger_type="scheduled_trigger") == author


class TestComputeDeniedNodesWithStubEvaluator:
    """compute_denied_nodes fans one per-kind verdict out to every node of that kind."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_evaluator(self) -> None:
        assert (
            await compute_denied_nodes(
                _db_stub(),
                None,
                definition=_definition(),
                project_id=uuid4(),
                principal_id=PRINCIPAL_ID,
            )
            == []
        )

    @pytest.mark.asyncio
    async def test_skips_evaluation_when_no_action_kinds(self) -> None:
        definition = {"nodes": [{"id": "gate", "type": "condition"}]}
        evaluator = MagicMock()
        assert (
            await compute_denied_nodes(
                _db_stub(),
                evaluator,
                definition=definition,
                project_id=None,
                principal_id=PRINCIPAL_ID,
            )
            == []
        )
        evaluator.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_one_evaluation_per_kind_fanned_out_to_nodes(self) -> None:
        with patch(
            "syntara.workflows.node_launch_checks.denied_node_kinds",
            AsyncMock(return_value=[NodeKindDenial(kind="script", denied_by="no-scripts", reason="policy_deny")]),
        ) as mock_denied:
            result = await compute_denied_nodes(
                _db_stub(),
                MagicMock(),
                definition=_definition(),
                project_id=uuid4(),
                principal_id=PRINCIPAL_ID,
            )

        assert result == [
            {"node_id": "script_a", "kind": "script", "denied_by": "no-scripts"},
            {"node_id": "script_b", "kind": "script", "denied_by": "no-scripts"},
        ]
        # Only action kinds are evaluated, and each distinct kind exactly once.
        assert mock_denied.await_args is not None
        assert sorted(mock_denied.await_args.kwargs["kinds"]) == ["http_request", "script"]

    @pytest.mark.asyncio
    async def test_passes_principal_labels_and_metadata(self) -> None:
        user = MagicMock(labels={"team": "infra"}, authz_metadata={"clearance": "low"})
        with patch(
            "syntara.workflows.node_launch_checks.denied_node_kinds",
            AsyncMock(return_value=[]),
        ) as mock_denied:
            await compute_denied_nodes(
                _db_stub(user=user),
                MagicMock(),
                definition=_definition(),
                project_id=uuid4(),
                principal_id=PRINCIPAL_ID,
            )

        assert mock_denied.await_args is not None
        kwargs = mock_denied.await_args.kwargs
        assert kwargs["user_labels"] == {"team": "infra"}
        assert kwargs["user_metadata"] == {"clearance": "low"}
        assert kwargs["project_name"] == "proj"
        assert kwargs["action"] == "execute"


class TestLoadPrincipalAuthzContext:
    """Principals may be users, service accounts, or neither."""

    @pytest.mark.asyncio
    async def test_service_account_contributes_labels_only(self) -> None:
        sa = MagicMock(labels={"tier": "ci"})
        db = _db_stub(user=None, service_account=sa)
        assert await load_principal_authz_context(db, PRINCIPAL_ID) == ({"tier": "ci"}, {})

    @pytest.mark.asyncio
    async def test_unknown_principal_yields_empty_context(self) -> None:
        db = _db_stub(user=None, service_account=None)
        assert await load_principal_authz_context(db, PRINCIPAL_ID) == ({}, {})


class _RegoEvaluatorStub:
    """AuthzEvaluator that runs the real bundled Rego policy via regopy."""

    def start(self) -> None:
        """No setup needed: evaluate_policy_input builds its own interpreter."""

    async def stop(self) -> None:
        """No resources to release."""

    async def health(self) -> bool:
        """Always ready."""
        return True

    def evaluate(self, authz_input: dict[str, Any]) -> dict[str, Any]:
        """Evaluate against the real policy."""
        return evaluate_policy_input(authz_input)


class TestComputeDeniedNodesWithRealRego:
    """The denied set comes out of the real policy, not a stub verdict."""

    @staticmethod
    def _patch_policies(statements: list[dict[str, Any]]) -> Any:  # noqa: ANN401
        return patch(
            "syntara.authz.engine.resolve_effective_policies",
            AsyncMock(return_value=statements),
        )

    @pytest.mark.asyncio
    async def test_authenticated_user_is_allowed_every_kind(self) -> None:
        with (
            self._patch_policies(policies_for_role("authenticated")),
            patch("syntara.authz.engine.resolve_user_groups", AsyncMock(return_value=[])),
        ):
            assert (
                await compute_denied_nodes(
                    _db_stub(project_name=""),
                    _RegoEvaluatorStub(),
                    definition=_definition(),
                    project_id=None,
                    principal_id=PRINCIPAL_ID,
                )
                == []
            )

    @pytest.mark.asyncio
    async def test_deny_on_script_kind_denies_only_script_nodes(self) -> None:
        statements = [
            *policies_for_role("authenticated"),
            {
                **deny_policy(
                    "no-scripts",
                    ["workflow_node:execute"],
                    conditions={"resource_labels": {"kind": "script"}},
                ),
            },
        ]
        with (
            self._patch_policies(statements),
            patch("syntara.authz.engine.resolve_user_groups", AsyncMock(return_value=[])),
        ):
            denied = await compute_denied_nodes(
                _db_stub(project_name=""),
                _RegoEvaluatorStub(),
                definition=_definition(),
                project_id=None,
                principal_id=PRINCIPAL_ID,
            )

        assert [entry["node_id"] for entry in denied] == ["script_a", "script_b"]
        assert {entry["kind"] for entry in denied} == {"script"}
        assert all(entry["denied_by"] == "no-scripts" for entry in denied)

    @pytest.mark.asyncio
    async def test_publisher_and_caller_can_get_different_verdicts(self) -> None:
        """The same definition yields different denied sets for two principals."""
        caller_statements = policies_for_role("authenticated")
        publisher_statements = [
            *policies_for_role("authenticated"),
            deny_policy(
                "publisher-no-http",
                ["workflow_node:execute"],
                conditions={"resource_labels": {"kind": "http_request"}},
            ),
        ]

        async def _by_principal(_db: Any, principal_id: UUID, **_kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401
            return publisher_statements if principal_id == PUBLISHER_ID else caller_statements

        with (
            patch("syntara.authz.engine.resolve_effective_policies", AsyncMock(side_effect=_by_principal)),
            patch("syntara.authz.engine.resolve_user_groups", AsyncMock(return_value=[])),
        ):
            caller_denied = await compute_denied_nodes(
                _db_stub(project_name=""),
                _RegoEvaluatorStub(),
                definition=_definition(),
                project_id=None,
                principal_id=PRINCIPAL_ID,
            )
            publisher_denied = await compute_denied_nodes(
                _db_stub(project_name=""),
                _RegoEvaluatorStub(),
                definition=_definition(),
                project_id=None,
                principal_id=PUBLISHER_ID,
            )

        assert caller_denied == []
        assert [entry["node_id"] for entry in publisher_denied] == ["call"]


class TestPermissionCheckEdgeRule:
    """The shape rule the definition validator should enforce for permission_check."""

    def test_valid_node_reports_no_problems(self) -> None:
        definition = {
            "nodes": [
                {"id": "step", "type": "script"},
                {"id": "check", "type": "permission_check"},
                {"id": "ok", "type": "script"},
                {"id": "nope", "type": "script"},
            ],
            "edges": [
                {"from": "step", "to": "check"},
                {"from": "check", "to": "ok", "from_port": "allowed"},
                {"from": "check", "to": "nope", "from_port": "denied"},
            ],
        }
        assert validate_permission_check_edges(definition) == []

    def test_reports_wrong_incoming_edge_count(self) -> None:
        definition = {
            "nodes": [{"id": "check", "type": "permission_check"}],
            "edges": [{"from": "a", "to": "check"}, {"from": "b", "to": "check"}],
        }
        problems = validate_permission_check_edges(definition)
        assert [node_id for node_id, _ in problems] == ["check"]
        assert "exactly one incoming edge" in problems[0][1]

    def test_reports_invalid_output_port(self) -> None:
        definition = {
            "nodes": [{"id": "check", "type": "permission_check"}],
            "edges": [
                {"from": "a", "to": "check"},
                {"from": "check", "to": "next", "from_port": "true"},
            ],
        }
        problems = validate_permission_check_edges(definition)
        assert "invalid output port" in problems[0][1]

    def test_no_permission_check_nodes_is_a_no_op(self) -> None:
        assert validate_permission_check_edges(_definition()) == []
        assert validate_permission_check_edges(None) == []


class TestEvaluatorRegistry:
    """The worker-side evaluator registry is a plain process-wide slot."""

    def test_set_and_clear(self) -> None:
        previous = get_node_authz_evaluator()
        try:
            sentinel: Any = _RegoEvaluatorStub()
            set_node_authz_evaluator(sentinel)
            assert get_node_authz_evaluator() is sentinel
            set_node_authz_evaluator(None)
            assert get_node_authz_evaluator() is None
        finally:
            set_node_authz_evaluator(previous)
