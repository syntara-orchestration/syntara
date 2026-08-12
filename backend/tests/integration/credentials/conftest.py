"""Shared fixtures for credential integration tests."""

from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.models import Project
from syntara.credentials.models.credential_type import CredentialType


@pytest_asyncio.fixture(scope="session")
async def test_session_factory(test_db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory for credential rotation tests.

    The rotate_keys module uses a module-level _session_factory that needs to be
    overridden for testing. This fixture provides a factory bound to the test database.
    """
    return async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def test_project_id(test_db_session: AsyncSession) -> str:
    """Create a test project and return its ID as a string.

    All credentials require a project_id (Option B — no global credentials).
    This fixture provides a default project for tests that don't care about
    project isolation specifically.
    """
    project = Project(name=f"test-project-{uuid4().hex[:8]}", description="Test project for credentials")
    test_db_session.add(project)
    await test_db_session.commit()
    await test_db_session.refresh(project)
    return str(project.id)


@pytest_asyncio.fixture
async def bearer_type(test_db_session: AsyncSession) -> CredentialType:
    """Create a bearer token credential type for testing."""
    ct = CredentialType(
        name=f"Test Bearer Token {uuid4().hex[:8]}",
        description="Test bearer token type",
        inputs={
            "fields": [
                {"id": "token", "label": "Token", "type": "string", "secret": True},
                {"id": "host", "label": "Host", "type": "string", "secret": False},
            ],
            "required": ["token"],
        },
        injectors={"extra_vars": {"bearer_token": "{{token}}"}, "env": {}, "file": {}},
        managed=False,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct


@pytest_asyncio.fixture
async def basic_auth_type(test_db_session: AsyncSession) -> CredentialType:
    """Create a basic auth credential type with mixed secret/non-secret fields."""
    ct = CredentialType(
        name=f"Test Basic Auth {uuid4().hex[:8]}",
        description="Test basic auth type",
        inputs={
            "fields": [
                {"id": "username", "label": "Username", "type": "string", "secret": False},
                {"id": "password", "label": "Password", "type": "string", "secret": True},
            ],
            "required": ["username", "password"],
        },
        injectors={
            "extra_vars": {"basic_username": "{{username}}", "basic_password": "{{password}}"},
            "env": {},
            "file": {},
        },
        managed=False,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct


@pytest_asyncio.fixture
async def ssh_key_type(test_db_session: AsyncSession) -> CredentialType:
    """Create an SSH key credential type."""
    ct = CredentialType(
        name=f"Test SSH Key {uuid4().hex[:8]}",
        description="Test SSH key type",
        inputs={
            "fields": [
                {"id": "username", "label": "Username", "type": "string", "secret": False},
                {"id": "ssh_key", "label": "SSH Private Key", "type": "string", "secret": True},
                {"id": "passphrase", "label": "Passphrase", "type": "string", "secret": True},
            ],
            "required": ["username", "ssh_key"],
        },
        injectors={"extra_vars": {}, "env": {}, "file": {"ssh_key": "{{ssh_key}}"}},
        managed=False,
    )
    test_db_session.add(ct)
    await test_db_session.commit()
    await test_db_session.refresh(ct)
    return ct
