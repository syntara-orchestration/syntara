"""Unit tests for engine-level credential:use fast-path helpers.

Covers _has_direct_system_credential_use, resolve_credential_use_visibility
fast path, and builtin_roles_with_system_grant — all pure-Python / mock-DB,
no OPA evaluation needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.authz.engine import VisibilityResult, _has_direct_system_credential_use, resolve_credential_use_visibility
from syntara.authz.role_conventions import builtin_roles_with_system_grant


def _mock_db(role_names: list[str]) -> AsyncMock:
    """Return a mock AsyncSession whose exec() yields the given role names."""
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = role_names
    db.exec.return_value = result
    return db


# ---------------------------------------------------------------------------
# builtin_roles_with_system_grant
# ---------------------------------------------------------------------------


class TestBuiltinRolesWithSystemGrant:  # noqa: D101
    def test_credential_use_returns_admin(self) -> None:
        roles = builtin_roles_with_system_grant("credential", "use")
        assert "admin" in roles

    def test_project_scoped_roles_excluded(self) -> None:
        # project-admin has credential:use at project scope, not system scope
        roles = builtin_roles_with_system_grant("credential", "use")
        assert "project-admin" not in roles
        assert "project-user" not in roles

    def test_unknown_resource_returns_empty(self) -> None:
        roles = builtin_roles_with_system_grant("nonexistent_resource", "use")
        assert len(roles) == 0

    def test_unknown_action_returns_empty(self) -> None:
        roles = builtin_roles_with_system_grant("credential", "nonexistent_action")
        assert len(roles) == 0

    def test_returns_frozenset(self) -> None:
        roles = builtin_roles_with_system_grant("credential", "use")
        assert isinstance(roles, frozenset)


# ---------------------------------------------------------------------------
# _has_direct_system_credential_use
# ---------------------------------------------------------------------------


class TestHasDirectSystemCredentialUse:  # noqa: D101
    @pytest.mark.asyncio
    async def test_admin_role_returns_true(self) -> None:
        db = _mock_db(["admin"])
        assert await _has_direct_system_credential_use(db, uuid4()) is True

    @pytest.mark.asyncio
    async def test_auditor_role_returns_false(self) -> None:
        db = _mock_db(["auditor"])
        assert await _has_direct_system_credential_use(db, uuid4()) is False

    @pytest.mark.asyncio
    async def test_no_roles_returns_false(self) -> None:
        db = _mock_db([])
        assert await _has_direct_system_credential_use(db, uuid4()) is False

    @pytest.mark.asyncio
    async def test_mixed_roles_with_admin_returns_true(self) -> None:
        db = _mock_db(["auditor", "admin"])
        assert await _has_direct_system_credential_use(db, uuid4()) is True


# ---------------------------------------------------------------------------
# resolve_credential_use_visibility — fast path (single DB query)
# ---------------------------------------------------------------------------


class TestResolveCredentialUseVisibilityFastPath:  # noqa: D101
    @pytest.mark.asyncio
    async def test_admin_takes_fast_path_unrestricted(self) -> None:
        db = _mock_db(["admin"])
        evaluator = MagicMock()

        result = await resolve_credential_use_visibility(db, evaluator, uuid4())

        assert result.unrestricted is True
        # Evaluator must NOT be called — the fast path skips OPA entirely
        evaluator.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_falls_through_to_full_path(self) -> None:
        """Auditor has no system-scope credential:use — falls through to resolve_effective_policies.

        This test verifies the fast-path guard works correctly by checking that
        the function does not return early. The full path requires a real DB so
        we let it raise (AsyncMock returns another mock on the second exec call)
        and just confirm the fast path guard did not short-circuit.
        """
        # First exec() call: _has_direct_system_credential_use → ["auditor"]
        # Subsequent exec() calls: resolve_effective_policies internals (mocked)
        db = AsyncMock()
        fast_path_result = MagicMock()
        fast_path_result.all.return_value = ["auditor"]

        # resolve_effective_policies makes several DB calls; return empty results
        # so _derive_allowed_projects returns ([], False) → empty project list
        empty_result = MagicMock()
        empty_result.all.return_value = []
        empty_result.first.return_value = None

        db.exec.side_effect = [fast_path_result, empty_result, empty_result, empty_result]

        evaluator = MagicMock()
        result = await resolve_credential_use_visibility(db, evaluator, uuid4())

        # Non-admin with no project grants → unrestricted=False, empty project list
        assert result.unrestricted is False

    @pytest.mark.asyncio
    async def test_full_path_system_grant_returns_unrestricted(self) -> None:
        """User admin-via-group: fast path misses, full path resolves unrestricted."""
        db = _mock_db(["auditor"])  # fast path: auditor has no system credential:use
        evaluator = MagicMock()

        system_policy = {"effect": "allow", "actions": ["credential:use"], "scope": "any"}
        with patch("syntara.authz.engine.resolve_effective_policies", return_value=[system_policy]):
            result = await resolve_credential_use_visibility(db, evaluator, uuid4())

        assert result.unrestricted is True

    @pytest.mark.asyncio
    async def test_deny_policy_falls_back_to_rego(self) -> None:
        """Deny policy in effective policies triggers the Rego fallback (line 566)."""
        db = _mock_db(["auditor"])
        evaluator = MagicMock()

        deny_policy = {"effect": "deny", "actions": ["credential:use"], "scope": "any"}
        rego_result = VisibilityResult(unrestricted=True)

        with (
            patch("syntara.authz.engine.resolve_effective_policies", return_value=[deny_policy]),
            patch("syntara.authz.engine.resolve_visibility", return_value=rego_result) as mock_rego,
        ):
            result = await resolve_credential_use_visibility(db, evaluator, uuid4())

        mock_rego.assert_called_once()
        assert result.unrestricted is True

    @pytest.mark.asyncio
    async def test_project_scoped_grant_resolves_project_ids(self) -> None:
        """Project-scoped credential:use grant resolves project names to IDs."""
        db = _mock_db(["auditor"])
        evaluator = MagicMock()
        project_id = uuid4()

        project_policy = {
            "effect": "allow",
            "actions": ["credential:use"],
            "scope": "project",
            "project": "proj-a",
        }

        with (
            patch("syntara.authz.engine.resolve_effective_policies", return_value=[project_policy]),
            patch("syntara.authz.engine._resolve_project_ids", return_value=[project_id]) as mock_resolve,
        ):
            result = await resolve_credential_use_visibility(db, evaluator, uuid4())

        mock_resolve.assert_called_once_with(db, ["proj-a"])
        assert result.unrestricted is False
        assert result.allowed_project_ids == [project_id]
