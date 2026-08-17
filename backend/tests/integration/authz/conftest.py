"""Shared fixtures for unit-level authz tests.

Provides helpers to evaluate the authz.rego policy via the Rego CLI
without any database or API dependencies, plus common fixtures for
engine/cache tests that use a mocked authz evaluator.
"""

import json
import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz import resource_actions as _resource_actions
from syntara.authz.resource_actions import _set_registry
from syntara.authz.seed import seed_authz_data

# ---------------------------------------------------------------------------
# Resource-actions registry — integration tests bypass app startup, so we
# install a registry with the pairs that appear in test statements. This is
# done per-test with save/restore (see ``_install_test_resource_actions``)
# rather than at import time: the registry is a process-global, and a permanent
# module-level mutation here leaks into other tests sharing the worker process
# under xdist (notably the unit ``test_resource_actions`` suite, which validates
# against the full application registry and fails when it sees this stub).
# ---------------------------------------------------------------------------
_TEST_RESOURCE_ACTIONS: dict[str, list[str]] = {
    "execution": ["create", "delete", "read", "run", "write"],
    "group": ["create", "delete", "read", "write"],
    "project": ["create", "delete", "read", "write"],
    "role-assignment": ["create", "delete", "read"],
    "setting": ["read", "write"],
    "user": ["create", "delete", "read", "write"],
    "workflow": ["create", "delete", "read", "run", "write"],
}


@pytest.fixture(autouse=True)
def _install_test_resource_actions() -> Generator[None, None, None]:
    """Install the test resource-actions registry for one test, then restore.

    Snapshots the process-global registry state, installs the test registry for
    the duration of the test, and restores the previous state on teardown so the
    stub never leaks into other tests running in the same process.
    """
    saved = (
        _resource_actions._registry,
        _resource_actions._all_pairs,
        _resource_actions._project_eligible,
    )
    _set_registry(
        _TEST_RESOURCE_ACTIONS,
        project_eligible=frozenset({"workflow", "execution", "project"}),
    )
    try:
        yield
    finally:
        (
            _resource_actions._registry,
            _resource_actions._all_pairs,
            _resource_actions._project_eligible,
        ) = saved


# Path to the rego policy file
_REGO_POLICY_PATH = Path(__file__).resolve().parents[3] / "src" / "syntara" / "authz" / "rego" / "authz.rego"

# Fields we care about from Rego evaluation
_Rego_RESULT_FIELDS = {"allow", "deny", "matched_policy", "denial_reason", "denied_by", "allowed_projects"}


@pytest.fixture
async def seeded_db(test_db_session: AsyncSession) -> AsyncSession:
    """Seed authz data and return the session."""
    await seed_authz_data(test_db_session)
    return test_db_session


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    """Create a mock authz evaluator."""
    opa = AsyncMock()
    opa.evaluate = MagicMock(
        return_value={
            "allow": True,
            "deny": False,
            "matched_policy": "test-allow",
            "denial_reason": "",
            "denied_by": "",
            "allowed_projects": ["*"],
        }
    )
    return opa


@pytest.fixture(autouse=True)
def _skip_if_no_opa() -> None:
    """Skip tests when Rego CLI is not available."""
    if not shutil.which("opa"):
        pytest.skip("opa CLI not found on PATH")


def _opa_evaluate(opa_input: dict[str, Any]) -> dict[str, Any]:
    """Evaluate authz using the Rego CLI against the real rego policy.

    Shells out to ``opa eval`` so the unit tests exercise the actual
    rego rules without needing a running authz evaluator.
    """
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "opa",
            "eval",
            "-d",
            str(_REGO_POLICY_PATH),
            "-I",
            "--format",
            "json",
            "data.orchestrator.authz",
        ],
        input=json.dumps(opa_input),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        msg = f"opa eval failed (rc={result.returncode}): {result.stderr}"
        raise RuntimeError(msg)

    raw = json.loads(result.stdout)
    value: dict[str, Any] = raw["result"][0]["expressions"][0]["value"]
    return {k: v for k, v in value.items() if k in _Rego_RESULT_FIELDS}


@pytest.fixture
def opa_evaluate() -> Any:  # noqa: ANN401
    """Fixture that returns the Rego evaluation function."""
    return _opa_evaluate


def build_opa_input(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    resource_project: str = "",
    resource_labels: dict[str, str] | None = None,
    resource_metadata: dict[str, Any] | None = None,
    user_id: str = "test-user-id",
    user_labels: dict[str, str] | None = None,
    user_metadata: dict[str, Any] | None = None,
    groups: list[dict[str, Any]] | None = None,
    effective_policies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an Rego input dict matching engine.py:79-95 format."""
    return {
        "user": {
            "id": user_id,
            "labels": user_labels or {},
            "metadata": user_metadata or {},
        },
        "action": action,
        "resource": {
            "type": resource_type,
            "id": resource_id,
            "project": resource_project,
            "labels": resource_labels or {},
            "metadata": resource_metadata or {},
        },
        "groups": groups or [],
        "effective_policies": effective_policies or [],
    }


def allow_policy(
    name: str,
    actions: list[str],
    scope: str = "any",
    *,
    conditions: dict[str, Any] | None = None,
    project: str = "",
) -> dict[str, Any]:
    """Build an allow policy statement dict."""
    stmt: dict[str, Any] = {
        "name": name,
        "effect": "allow",
        "actions": actions,
        "scope": scope,
    }
    if project:
        stmt["project"] = project
    if conditions is not None:
        stmt["conditions"] = conditions
    return stmt


def deny_policy(
    name: str,
    actions: list[str],
    scope: str = "any",
    *,
    conditions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deny policy statement dict."""
    stmt: dict[str, Any] = {
        "name": name,
        "effect": "deny",
        "actions": actions,
        "scope": scope,
    }
    if conditions is not None:
        stmt["conditions"] = conditions
    return stmt


def policies_for_role(role_name: str) -> list[dict[str, Any]]:
    """Resolve policy statements for a built-in role without DB access."""
    from syntara.authz.role_conventions import builtin_role_policy_names, resolve_builtin_policy_statements

    policy_names = builtin_role_policy_names(role_name)
    if not policy_names:
        msg = f"Unknown built-in role: {role_name}"
        raise ValueError(msg)

    result: list[dict[str, Any]] = []
    for policy_name in policy_names:
        for stmt in resolve_builtin_policy_statements(policy_name):
            result.append({**stmt, "name": policy_name})
    return result
