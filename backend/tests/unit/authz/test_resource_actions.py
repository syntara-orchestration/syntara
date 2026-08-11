"""Tests for the dynamic resource_actions registry.

Validates that the scanner (``build_resource_actions``) correctly
discovers resource-action pairs from PermissionChecker / ProjectScopeFilter
route dependencies and BUILTIN_POLICIES, and that ``validate_statements``
works against the resulting registry.
"""

import re
from pathlib import Path

import pytest
import yaml
from fastapi import Depends

from syntara.authz.resource_actions import (
    build_resource_actions,
    get_all_resource_action_pairs,
    get_resource_actions,
    validate_statements,
)
from syntara.authz.role_conventions import BUILTIN_POLICIES

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "syntara"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PERM_CHECKER_RE = re.compile(r'PermissionChecker\(\s*"([^"]+)"\s*,\s*"([^"]+)"')


def _iter_router_files() -> list[Path]:
    """Yield Python files that match the Router Discovery Framework conventions."""
    files: list[Path] = []
    files.extend(_SRC_ROOT.glob("*/*router.py"))
    api_v1 = _SRC_ROOT / "api" / "v1"
    if api_v1.is_dir():
        files.extend(p for p in api_v1.glob("*.py") if p.stem not in {"__init__", "utils", "websocket"})
    return files


def _collect_permission_checker_pairs() -> list[tuple[str, str, str]]:
    """Scan router files for PermissionChecker("resource", "action")."""
    results: list[tuple[str, str, str]] = []
    for py_file in _iter_router_files():
        text = py_file.read_text()
        for match in _PERM_CHECKER_RE.finditer(text):
            resource_type, action = match.group(1), match.group(2)
            location = f"{py_file.relative_to(_SRC_ROOT.parent)}:{text[: match.start()].count(chr(10)) + 1}"
            results.append((resource_type, action, location))
    return results


def _collect_openapi_permission_pairs() -> list[tuple[str, str, str]]:
    """Extract x-app-permission pairs from the aggregated OpenAPI spec."""
    results: list[tuple[str, str, str]] = []
    spec_file = _SRC_ROOT / "schemas" / "openapi.yaml"
    doc = yaml.safe_load(spec_file.read_text())
    if not isinstance(doc, dict):
        return results
    for path, methods in (doc.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, spec in methods.items():
            if not isinstance(spec, dict):
                continue
            perm = spec.get("x-app-permission")
            if not isinstance(perm, dict):
                continue
            resource = perm.get("resource")
            action = perm.get("action")
            if resource and action:
                location = f"schemas/openapi.yaml {method.upper()} {path}"
                results.append((resource, action, location))
    return results


# ============================================================================
# Structural invariants of the built registry
# ============================================================================


class TestResourceActionsRegistry:
    """Verify structural invariants of the dynamically built registry."""

    def test_resource_types_sorted(self) -> None:
        registry = get_resource_actions()
        keys = list(registry.keys())
        assert keys == sorted(keys)

    def test_actions_sorted_within_each_resource(self) -> None:
        for rt, actions in get_resource_actions().items():
            assert actions == sorted(actions), f"Actions for '{rt}' are not sorted"

    def test_no_empty_action_lists(self) -> None:
        for rt, actions in get_resource_actions().items():
            assert len(actions) > 0, f"Resource type '{rt}' has no actions"

    def test_no_duplicate_actions(self) -> None:
        for rt, actions in get_resource_actions().items():
            assert len(actions) == len(set(actions)), f"Duplicate actions in '{rt}'"


# ============================================================================
# get_all_resource_action_pairs
# ============================================================================


class TestGetAllResourceActionPairs:
    """Verify the flattened helper."""

    def test_returns_set_of_strings(self) -> None:
        pairs = get_all_resource_action_pairs()
        assert isinstance(pairs, frozenset)
        assert all(isinstance(p, str) for p in pairs)

    def test_all_pairs_have_colon(self) -> None:
        for pair in get_all_resource_action_pairs():
            assert ":" in pair, f"Pair '{pair}' missing colon separator"

    def test_count_matches_registry(self) -> None:
        registry = get_resource_actions()
        expected = sum(len(actions) for actions in registry.values())
        assert len(get_all_resource_action_pairs()) == expected


# ============================================================================
# Registry includes all BUILTIN_POLICIES pairs
# ============================================================================


class TestRegistrySyncWithBuiltinPolicies:
    """Every resource:action from built-in policies must be in the registry."""

    def test_all_builtin_policy_pairs_covered(self) -> None:
        registry_pairs = get_all_resource_action_pairs()
        missing = []
        for policy in BUILTIN_POLICIES:
            pair = f"{policy.resource}:{policy.action}"
            if pair not in registry_pairs:
                missing.append(pair)
        assert missing == [], f"Built-in policy pairs missing from registry: {missing}"


# ============================================================================
# validate_statements
# ============================================================================


class TestValidateStatements:
    """Verify runtime validation of policy statement action strings."""

    def test_valid_actions_return_empty(self) -> None:
        stmts = [{"actions": ["workflow:read", "credential:delete"]}]
        assert validate_statements(stmts) == []

    def test_invalid_action_detected(self) -> None:
        stmts = [{"actions": ["spaceship:launch"]}]
        result = validate_statements(stmts)
        assert result == ["spaceship:launch"]

    def test_invalid_resource_type_detected(self) -> None:
        stmts = [{"actions": ["nonexistent:read"]}]
        result = validate_statements(stmts)
        assert result == ["nonexistent:read"]

    def test_wildcard_allowed_for_registered_resource(self) -> None:
        stmts = [{"actions": ["workflow:*"]}]
        assert validate_statements(stmts) == []

    def test_wildcard_rejected_for_unregistered_resource(self) -> None:
        stmts = [{"actions": ["spaceship:*"]}]
        result = validate_statements(stmts)
        assert result == ["spaceship:*"]

    def test_missing_colon_rejected(self) -> None:
        stmts = [{"actions": ["justanaction"]}]
        result = validate_statements(stmts)
        assert result == ["justanaction"]

    def test_multiple_statements_validated(self) -> None:
        stmts = [
            {"actions": ["workflow:read"]},
            {"actions": ["fake:action", "credential:read"]},
        ]
        result = validate_statements(stmts)
        assert result == ["fake:action"]

    def test_empty_statements_valid(self) -> None:
        assert validate_statements([]) == []

    def test_statement_without_actions_key(self) -> None:
        assert validate_statements([{"effect": "allow"}]) == []


# ============================================================================
# Scanner captures all PermissionChecker pairs from source code
# ============================================================================


class TestSyncWithPermissionCheckers:
    """Every PermissionChecker in the codebase must appear in the dynamic registry."""

    def test_all_permission_checker_pairs_registered(self) -> None:
        registry_pairs = get_all_resource_action_pairs()
        missing = []
        for resource_type, action, location in _collect_permission_checker_pairs():
            pair = f"{resource_type}:{action}"
            if pair not in registry_pairs:
                missing.append(f"{pair} (at {location})")
        assert missing == [], "PermissionChecker references unregistered resource-action pairs:\n" + "\n".join(
            f"  - {m}" for m in missing
        )


# ============================================================================
# Scanner captures all OpenAPI x-app-permission pairs
# ============================================================================


class TestSyncWithOpenAPISpecs:
    """Every x-app-permission in OpenAPI specs must appear in the dynamic registry."""

    def test_all_openapi_permission_pairs_registered(self) -> None:
        registry_pairs = get_all_resource_action_pairs()
        missing = []
        for resource_type, action, location in _collect_openapi_permission_pairs():
            pair = f"{resource_type}:{action}"
            if pair not in registry_pairs:
                missing.append(f"{pair} (at {location})")
        assert missing == [], "OpenAPI x-app-permission references unregistered resource-action pairs:\n" + "\n".join(
            f"  - {m}" for m in missing
        )


# ============================================================================
# build_resource_actions scanner tests
# ============================================================================


class TestBuildResourceActions:
    """Test the scanner function directly with controlled inputs."""

    def test_discovers_permission_checker_from_route(self) -> None:
        from fastapi import FastAPI

        from syntara.authz.dependencies import PermissionChecker

        app = FastAPI()
        checker = PermissionChecker("test-resource", "test-action")

        @app.get("/test", dependencies=[Depends(checker)])
        async def _test_endpoint() -> dict[str, str]:
            return {}

        result = build_resource_actions(app)
        assert "test-resource" in result
        assert "test-action" in result["test-resource"]

    def test_discovers_project_scope_filter_from_route(self) -> None:
        from typing import Annotated

        from fastapi import FastAPI

        from syntara.authz.dependencies import ProjectScopeFilter
        from syntara.authz.engine import AllowedProjectsResult

        app = FastAPI()

        @app.get("/test")
        async def _test_endpoint(
            _allowed: Annotated[AllowedProjectsResult, Depends(ProjectScopeFilter("scoped-res", "list"))],
        ) -> dict[str, str]:
            return {}

        result = build_resource_actions(app)
        assert "scoped-res" in result
        assert "list" in result["scoped-res"]

    def test_includes_builtin_policies(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        result = build_resource_actions(app)

        builtin_pairs: set[tuple[str, str]] = set()
        for policy in BUILTIN_POLICIES:
            builtin_pairs.add((policy.resource, policy.action))

        for resource, action in builtin_pairs:
            assert resource in result, f"Missing resource '{resource}' from BUILTIN_POLICIES"
            assert action in result[resource], f"Missing action '{action}' for resource '{resource}'"

    def test_result_is_sorted(self) -> None:
        from fastapi import FastAPI

        app = FastAPI()
        result = build_resource_actions(app)

        assert list(result.keys()) == sorted(result.keys())
        for actions in result.values():
            assert actions == sorted(actions)

    def test_raises_before_initialization(self) -> None:
        import syntara.authz.resource_actions as mod

        old_registry = mod._registry
        old_pairs = mod._all_pairs
        try:
            mod._registry = None
            mod._all_pairs = frozenset()
            with pytest.raises(RuntimeError, match="not initialized"):
                get_resource_actions()
            with pytest.raises(RuntimeError, match="not initialized"):
                get_all_resource_action_pairs()
        finally:
            mod._registry = old_registry
            mod._all_pairs = old_pairs
