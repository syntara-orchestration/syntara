"""Integration tests for AAP credential:use RBAC authorization.

These tests call resolve_aap_connection_from_credential with a real regopy-based
evaluator — not a mock of the authz path — to verify that the RBAC check grants
or denies access based on the caller's project roles. The deny path is testable
without a real secret because RBAC is checked before decryption.
"""

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.aap.credential_resolver import (
    AAP_CREDENTIAL_TYPE_NAME,
    resolve_aap_connection_from_credential,
)
from syntara.aap.exceptions import AAPAuthenticationError, AAPNotConfiguredError
from syntara.authz.evaluator import evaluate_policy_input
from syntara.authz.models import Project
from syntara.core.models import User
from syntara.credentials.models.credential import Credential
from syntara.credentials.models.credential_type import CredentialType
from tests.integration.api.conftest import (
    make_admin,
    make_auditor,
    make_project_user,
)


@pytest.fixture
def real_evaluator() -> AsyncMock:
    """Build an evaluator backed by regopy (the real rego policy, no HTTP OPA)."""
    evaluator = AsyncMock()
    evaluator.evaluate = MagicMock(side_effect=evaluate_policy_input)
    return evaluator


@pytest.fixture
async def aap_type(test_db_session: AsyncSession) -> CredentialType:
    ct = CredentialType(
        name=AAP_CREDENTIAL_TYPE_NAME,
        description="AAP credential type for RBAC tests",
        inputs={
            "fields": [
                {"id": "oauth_token", "label": "OAuth Token", "type": "string", "secret": True},
            ],
            "required": ["oauth_token"],
        },
        injectors={
            "extra_vars": {"aap_oauth_token": "{{ oauth_token }}"},
            "env": {},
            "file": {},
        },
        managed=True,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct


@pytest.fixture
async def aap_project(test_db_session: AsyncSession) -> Project:
    project = Project(name=f"aap-rbac-{uuid4().hex[:8]}", description="AAP RBAC test project")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return project


@pytest.fixture
async def aap_credential(
    test_db_session: AsyncSession,
    aap_type: CredentialType,
    aap_project: Project,
    user_factory: Callable[..., Awaitable[User]],
) -> Credential:
    creator = await user_factory()
    cred = Credential(
        name=f"aap-cred-{uuid4().hex[:8]}",
        credential_type_id=aap_type.id,
        project_id=aap_project.id,
        created_by=creator.id,
        enabled=True,
    )
    test_db_session.add(cred)
    await test_db_session.commit()
    await test_db_session.refresh(cred)
    return cred


class TestAAPCredentialRBAC:
    """resolve_aap_connection_from_credential enforces credential:use via real OPA."""

    @pytest.mark.asyncio
    async def test_auditor_denied_credential_use(
        self,
        test_db_session: AsyncSession,
        aap_credential: Credential,
        aap_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        real_evaluator: AsyncMock,
    ) -> None:
        """Auditor (credential:read, not credential:use) gets AAPAuthenticationError."""
        suffix = uuid4().hex[:4]
        auditor = await user_factory(username=f"auditor-aap-{suffix}", email=f"auditor-aap-{suffix}@test.com")
        await make_auditor(test_db_session, auditor)

        with pytest.raises(AAPAuthenticationError):
            await resolve_aap_connection_from_credential(
                session=test_db_session,
                credential_id=aap_credential.id,
                user_id=auditor.id,
                evaluator=real_evaluator,
                user_labels=auditor.labels,
                user_metadata=auditor.authz_metadata,
            )

    @pytest.mark.asyncio
    async def test_user_role_denied_credential_use(
        self,
        test_db_session: AsyncSession,
        aap_credential: Credential,
        aap_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        real_evaluator: AsyncMock,
    ) -> None:
        """User role (no credential permissions) gets AAPAuthenticationError."""
        user = await user_factory(username=f"user-aap-{uuid4().hex[:4]}", email=f"user-aap-{uuid4().hex[:4]}@test.com")

        with pytest.raises(AAPAuthenticationError):
            await resolve_aap_connection_from_credential(
                session=test_db_session,
                credential_id=aap_credential.id,
                user_id=user.id,
                evaluator=real_evaluator,
                user_labels=user.labels,
                user_metadata=user.authz_metadata,
            )

    @pytest.mark.asyncio
    async def test_project_user_granted_credential_use(
        self,
        test_db_session: AsyncSession,
        aap_credential: Credential,
        aap_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        real_evaluator: AsyncMock,
    ) -> None:
        """Project-user (credential:use at project scope) gets past RBAC.

        Fails at decryption (no secret stored) — not AAPAuthenticationError.
        """
        suffix = uuid4().hex[:4]
        proj_user = await user_factory(username=f"puser-aap-{suffix}", email=f"puser-aap-{suffix}@test.com")
        await make_project_user(test_db_session, proj_user, aap_project)

        with pytest.raises(AAPNotConfiguredError):
            await resolve_aap_connection_from_credential(
                session=test_db_session,
                credential_id=aap_credential.id,
                user_id=proj_user.id,
                evaluator=real_evaluator,
                user_labels=proj_user.labels,
                user_metadata=proj_user.authz_metadata,
            )

    @pytest.mark.asyncio
    async def test_admin_granted_credential_use(
        self,
        test_db_session: AsyncSession,
        aap_credential: Credential,
        aap_project: Project,
        user_factory: Callable[..., Awaitable[User]],
        real_evaluator: AsyncMock,
    ) -> None:
        """Admin (credential:use globally) gets past RBAC.

        Fails at decryption (no secret stored) — not AAPAuthenticationError.
        """
        suffix = uuid4().hex[:4]
        admin = await user_factory(username=f"admin-aap-{suffix}", email=f"admin-aap-{suffix}@test.com")
        await make_admin(test_db_session, admin)

        with pytest.raises(AAPNotConfiguredError):
            await resolve_aap_connection_from_credential(
                session=test_db_session,
                credential_id=aap_credential.id,
                user_id=admin.id,
                evaluator=real_evaluator,
                user_labels=admin.labels,
                user_metadata=admin.authz_metadata,
            )
