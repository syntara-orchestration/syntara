"""Unit tests for the Rego result cache."""

import time
from collections.abc import Generator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.engine import (
    AuthzRequest,
    _hash_authz_input,
    authorize,
    clear_authz_cache,
    init_authz_cache,
    resolve_allowed_projects,
)
from syntara.core.models import User


@pytest.fixture(autouse=True)
def _enable_cache() -> Generator[None, None, None]:
    """Enable the Rego cache for these tests."""
    init_authz_cache(enabled=True, ttl_seconds=10)
    yield
    clear_authz_cache()
    init_authz_cache(enabled=False)


class TestRegoCacheHitMiss:
    """Tests for Rego cache hit/miss behavior."""

    @pytest.mark.asyncio
    async def test_second_call_uses_cached_opa_result(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """Identical Rego input on second call skips evaluator.evaluate()."""
        request = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 1

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 1

    @pytest.mark.asyncio
    async def test_different_action_misses_cache(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """Different action produces different Rego input, so cache miss."""
        req1 = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )
        await authorize(seeded_db, mock_evaluator, req1)

        req2 = AuthzRequest(
            user_id=test_user.id,
            action="delete",
            resource_type="workflow",
            resource_id="wf-1",
        )
        await authorize(seeded_db, mock_evaluator, req2)
        assert mock_evaluator.evaluate.await_count == 2

    @pytest.mark.asyncio
    async def test_different_users_miss_cache(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """Different user_ids produce different effective policies, so cache miss."""
        req1 = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )
        await authorize(seeded_db, mock_evaluator, req1)

        other_user_id = uuid4()
        req2 = AuthzRequest(
            user_id=other_user_id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )
        with (
            patch(
                "syntara.authz.engine.resolve_effective_policies",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "syntara.authz.engine.resolve_user_groups",
                new_callable=AsyncMock,
                return_value=[],
            ),
        ):
            await authorize(seeded_db, mock_evaluator, req2)
        assert mock_evaluator.evaluate.await_count == 2


class TestRegoCacheDisabled:
    """Tests for disabled cache mode."""

    @pytest.fixture(autouse=True)
    def _disable(self) -> None:
        init_authz_cache(enabled=False)

    @pytest.mark.asyncio
    async def test_every_call_hits_opa(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """When cache is disabled, every call goes to Rego."""
        request = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )
        await authorize(seeded_db, mock_evaluator, request)
        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 2


class TestRegoCacheTTLExpiry:
    """Tests for TTL expiry behavior."""

    @pytest.fixture(autouse=True)
    def _short_ttl(self) -> Generator[None, None, None]:
        init_authz_cache(enabled=True, ttl_seconds=1)
        yield
        clear_authz_cache()
        init_authz_cache(enabled=False)

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """Cache entries expire after TTL, triggering fresh Rego call."""
        request = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 1

        time.sleep(1.1)  # noqa: ASYNC251

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 2


class TestClearRegoCache:
    """Tests for the clear_authz_cache utility."""

    @pytest.mark.asyncio
    async def test_clear_forces_fresh_call(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """clear_authz_cache() forces the next call to evaluate fresh."""
        request = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 1

        clear_authz_cache()

        await authorize(seeded_db, mock_evaluator, request)
        assert mock_evaluator.evaluate.await_count == 2


class TestHashRegoInput:
    """Tests for the _hash_authz_input helper."""

    def test_deterministic(self) -> None:
        """Same dict produces same hash."""
        opa_input = {"user": {"id": "abc"}, "action": "read", "groups": []}
        assert _hash_authz_input(opa_input) == _hash_authz_input(opa_input)

    def test_key_order_independent(self) -> None:
        """Dict key order doesn't affect hash."""
        input1 = {"action": "read", "user": {"id": "abc"}}
        input2 = {"user": {"id": "abc"}, "action": "read"}
        assert _hash_authz_input(input1) == _hash_authz_input(input2)

    def test_different_values_different_hash(self) -> None:
        """Different values produce different hashes."""
        input1 = {"user": {"id": "abc"}, "action": "read"}
        input2 = {"user": {"id": "abc"}, "action": "write"}
        assert _hash_authz_input(input1) != _hash_authz_input(input2)

    def test_list_order_independent(self) -> None:
        """List ordering doesn't affect hash — guards against DB query order variance."""
        input1 = {
            "groups": ["admin", "viewer"],
            "effective_policies": [
                {"role": "admin", "scope": "global"},
                {"role": "viewer", "scope": "project"},
            ],
        }
        input2 = {
            "groups": ["viewer", "admin"],
            "effective_policies": [
                {"role": "viewer", "scope": "project"},
                {"role": "admin", "scope": "global"},
            ],
        }
        assert _hash_authz_input(input1) == _hash_authz_input(input2)


class TestRegoCacheDefensiveCopy:
    """Tests that cached results are returned as copies."""

    @pytest.mark.asyncio
    async def test_cached_result_is_a_copy(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """Mutating a cached result does not affect subsequent cache hits."""
        request = AuthzRequest(
            user_id=test_user.id,
            action="read",
            resource_type="workflow",
            resource_id="wf-1",
        )

        result1 = await authorize(seeded_db, mock_evaluator, request)
        # Mutate the result object (simulating a careless caller)
        result1.matched_policy = "MUTATED"

        result2 = await authorize(seeded_db, mock_evaluator, request)
        assert result2.matched_policy == "test-allow"
        assert mock_evaluator.evaluate.await_count == 1


class TestResolveAllowedProjectsCache:
    """Tests for caching in resolve_allowed_projects."""

    @pytest.mark.asyncio
    async def test_resolve_allowed_projects_caches(
        self,
        seeded_db: AsyncSession,
        test_user: User,
        mock_evaluator: AsyncMock,
    ) -> None:
        """resolve_allowed_projects() uses cache on repeated calls."""
        await resolve_allowed_projects(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
        assert mock_evaluator.evaluate.await_count == 1

        await resolve_allowed_projects(seeded_db, mock_evaluator, test_user.id, "workflow", "read")
        assert mock_evaluator.evaluate.await_count == 1
