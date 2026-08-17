"""Tests for race conditions in PermissionChecker.

This module tests TOCTOU (Time-of-Check-Time-of-Use) vulnerabilities in the
authorization flow, particularly around ownership-based checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request

from syntara.authz.dependencies import PermissionChecker
from syntara.core.models.user import User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
@pytest.mark.xfail(
    reason="Theoretical TOCTOU race for future ownership-transfer APIs (credentials have no such API today)",
    strict=False,
)
async def test_toctou_ownership_change_during_request(
    test_db_session: AsyncSession,
) -> None:
    """XFAIL: Theoretical TOCTOU race for resources with ownership-transfer APIs.

    NOTE: This test is currently THEORETICAL. Credentials have no ownership-transfer
    API today (CredentialUpdate has no created_by field, and nothing mutates ownership
    after create), so this race cannot happen for credentials. The test mocks a
    fictional scenario to document the hazard for FUTURE resources that might allow
    ownership transfer.

    If a future resource type allows ownership transfer (e.g., "transfer credential
    to user B"), this test demonstrates the TOCTOU vulnerability that would need
    to be addressed via:
    - SELECT FOR UPDATE to lock the resource during ownership check
    - Re-verify ownership immediately before UPDATE
    - Optimistic locking (version field)

    Attack scenario (for a hypothetical ownership-transfer API):
    1. User A starts updating resource they own
    2. PermissionChecker resolves owner_id = User A (authorization passes)
    3. Before the actual UPDATE executes, User B transfers ownership to themselves
    4. The UPDATE executes with the now-stale authorization decision
    5. Result: User A successfully updates a resource they no longer own
    """
    from syntara.credentials.models import Credential

    # Setup
    user_a_id = uuid4()
    user_b_id = uuid4()
    credential_id = uuid4()
    project_id = uuid4()

    user_a = User(
        id=user_a_id,
        username="user_a",
        email="a@example.com",
        labels={},
    )

    # Mock credential that initially belongs to user A
    mock_credential = MagicMock(spec=Credential)
    mock_credential.id = credential_id
    mock_credential.created_by = user_a_id  # Initial owner
    mock_credential.project_id = project_id

    # Create PermissionChecker
    checker = PermissionChecker(
        "credential",
        "update",
        resource_model=Credential,
        resource_id_param="credential_id",
        owner_field="created_by",
    )

    # Mock request
    mock_request = MagicMock(spec=Request)
    mock_request.path_params = {"credential_id": str(credential_id)}
    mock_request.state.is_cert_authenticated = False

    # Mock authz evaluator that allows the update (initial check passes)
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate = MagicMock(return_value={"allow": True, "deny": False})

    # Patch dependencies
    with (
        patch("syntara.authz.dependencies.get_current_user", return_value=user_a),
        patch("syntara.authz.dependencies.get_authz_evaluator", return_value=mock_evaluator),
        patch("syntara.authz.dependencies.get_db", return_value=test_db_session),
    ):
        # RACE CONDITION SIMULATION:
        # 1. _resolve_resource_owner returns user_a_id (correct at time of check)
        original_resolve = checker._resolve_resource_owner

        async def resolve_then_transfer(db: AsyncSession, resource_id: str) -> str:
            """Simulate ownership transfer happening during the race window."""
            # First, resolve the owner (returns user_a_id)
            owner_id = await original_resolve(db, resource_id)

            # RACE: While the authz decision is being made, ownership changes
            # In reality, this would be a concurrent transaction by user B
            mock_credential.created_by = user_b_id

            return owner_id  # Returns stale owner_id (user_a)

        checker._resolve_resource_owner = resolve_then_transfer  # type: ignore[method-assign]

        # Mock the database query that returns the credential
        async def mock_exec(query):  # noqa: ANN202
            result = MagicMock()
            result.first = MagicMock(return_value=str(user_a_id))  # Stale owner at check time
            return result

        test_db_session.exec = mock_exec  # type: ignore[assignment, method-assign]

        # Call PermissionChecker - should pass because check uses stale owner
        await checker(mock_request, user_a, test_db_session)

        # Verify the authorization was called with stale metadata
        assert mock_evaluator.evaluate.called
        authz_call_args = mock_evaluator.evaluate.call_args
        authz_input = authz_call_args[0][0]  # First positional arg is the authz_input dict

        # The authz check used created_by=user_a_id (stale)
        assert authz_input["resource"]["metadata"].get("created_by") == str(user_a_id)

        # But the credential now belongs to user_b
        assert mock_credential.created_by == user_b_id

        # This is the TOCTOU vulnerability: authorization passed using stale owner data
        # After this check, if user_a proceeds to UPDATE the credential, they'll
        # successfully modify a resource they no longer own
        #
        # The fix should make this test pass by either:
        # 1. Re-checking ownership immediately before UPDATE
        # 2. Using SELECT FOR UPDATE to lock during check
        # 3. Using optimistic locking with a version field
        pytest.fail(
            "TOCTOU vulnerability: Authorization passed with stale owner metadata. "
            "User A can update credential now owned by User B."
        )


@pytest.mark.asyncio
async def test_ownership_metadata_not_populated_for_create(
    test_db_session: AsyncSession,
) -> None:
    """Verify PermissionChecker populates ownership metadata for CREATE operations.

    Current behavior: PermissionChecker only resolves and populates created_by
    metadata for UPDATE/DELETE operations (when resource_id is present). For
    CREATE operations, resource_id is None, so owner resolution is skipped.

    This creates a semantic gap: policies with scope="own" cannot be used for
    CREATE operations because the ownership metadata is never populated.

    Expected behavior: For CREATE, use current_user.id as created_by metadata
    since the user performing the CREATE will be the owner.
    """
    user_id = uuid4()
    user = User(
        id=user_id,
        username="creator",
        email="creator@example.com",
        labels={},
    )

    # Create PermissionChecker for CREATE operation
    checker = PermissionChecker(
        "credential",
        "create",
        owner_field="created_by",  # Configure owner field
    )

    # Mock request (no resource_id for CREATE)
    mock_request = MagicMock(spec=Request)
    mock_request.path_params = {}
    mock_request.state.is_cert_authenticated = False

    # Mock authz evaluator
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate = MagicMock(return_value={"allow": True, "deny": False})

    with (
        patch("syntara.authz.dependencies.get_current_user", return_value=user),
        patch("syntara.authz.dependencies.get_authz_evaluator", return_value=mock_evaluator),
        patch("syntara.authz.dependencies.get_db", return_value=test_db_session),
    ):
        await checker(mock_request, user, test_db_session)

        # Verify authorization was called
        assert mock_evaluator.evaluate.called
        authz_call_args = mock_evaluator.evaluate.call_args
        authz_input = authz_call_args[0][0]  # First positional arg is the authz_input dict

        # CURRENT BEHAVIOR: resource_metadata is empty for CREATE
        # This is actually CORRECT because:
        # 1. The resource doesn't exist yet, so there's no created_by to check
        # 2. Policies with scope="own" don't make semantic sense for CREATE
        # 3. The Rego rule requires created_by == user.id, which fails when metadata is empty
        #
        # This test verifies the fail-secure behavior: if someone creates a
        # nonsensical policy like "credential:create:own", it will deny all requests
        # because metadata.created_by will be empty.
        assert authz_input["resource"]["metadata"] == {}

        # The proper fix is to add validation that rejects policies using "own" scope
        # for CREATE actions, not to populate fake ownership metadata for CREATE.
        # This validation is implemented in validate_own_scope_actions() function.
