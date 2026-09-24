"""The denied-node list is bound by the workflow-auth HMAC (ANSTRAT-1750, AD-9).

``denied_nodes`` and ``run_principal_id`` are positional start arguments, and the
MAC covers a fingerprint of every argument, so an attacker who replays a captured
token with an emptied or edited denied list fails verification.
"""

import os
from collections.abc import Sequence
from typing import Any
from unittest.mock import patch

import pytest

from syntara.workflows.workflow_engine.workflow_auth import sign_workflow, verify_workflow

_TEST_KEY = os.urandom(32)
_WORKFLOW_ID = "wf-denied-1"
_WORKFLOW_TYPE = "orchestrator_workflow"

_DENIED = [{"node_id": "script_a", "kind": "script", "denied_by": "no-scripts"}]
_PRINCIPAL = "11111111-1111-4111-8111-111111111111"


def _start_args(
    denied_nodes: list[dict[str, Any]] | None = None,
    run_principal_id: str | None = _PRINCIPAL,
) -> list[Any]:
    """Build the positional argument list OrchestratorWorkflow.run is started with."""
    return [
        {"schema_version": "2.0.0", "nodes": [{"id": "script_a", "type": "script"}]},
        "exec-1",
        "trigger",
        {},
        False,
        None,
        None,
        None,
        {"workflow_context": {}},
        denied_nodes if denied_nodes is not None else _DENIED,
        run_principal_id,
    ]


@pytest.fixture(autouse=True)
def _fixed_key() -> Any:  # noqa: ANN401
    """Sign and verify with a deterministic key instead of the HKDF-derived one."""
    with patch(
        "syntara.workflows.workflow_engine.workflow_auth._get_signing_key",
        return_value=_TEST_KEY,
    ):
        yield


def _token(args: Sequence[Any]) -> bytes:
    return sign_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, args)


class TestDeniedNodesAreMacBound:
    """The MAC binds the denied list carried in the workflow input."""

    def test_untampered_args_verify(self) -> None:
        args = _start_args()
        assert verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, args, _token(args))

    def test_dropping_the_denied_list_fails_verification(self) -> None:
        token = _token(_start_args())
        tampered = _start_args(denied_nodes=[])
        assert not verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, tampered, token)

    def test_nulling_the_denied_list_fails_verification(self) -> None:
        token = _token(_start_args())
        tampered = _start_args()
        tampered[9] = None
        assert not verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, tampered, token)

    def test_editing_a_denied_entry_fails_verification(self) -> None:
        token = _token(_start_args())
        tampered = _start_args(
            denied_nodes=[{"node_id": "other_node", "kind": "script", "denied_by": "no-scripts"}],
        )
        assert not verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, tampered, token)

    def test_adding_a_denied_entry_fails_verification(self) -> None:
        token = _token(_start_args())
        tampered = _start_args(
            denied_nodes=[*_DENIED, {"node_id": "script_b", "kind": "script", "denied_by": "no-scripts"}],
        )
        assert not verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, tampered, token)

    def test_swapping_the_run_principal_fails_verification(self) -> None:
        token = _token(_start_args())
        tampered = _start_args(run_principal_id="99999999-9999-4999-8999-999999999999")
        assert not verify_workflow(_WORKFLOW_ID, _WORKFLOW_TYPE, tampered, token)
