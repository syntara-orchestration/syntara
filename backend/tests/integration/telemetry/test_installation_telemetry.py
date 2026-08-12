"""Integration tests for installation ID and anonymous ID derivation.

Tests cover:
- US1: After migration the installation table has exactly one row with a valid UUID
- US2: derive_anonymous_id() determinism, distinctness, and format
"""

import uuid

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models.installation import Installation
from syntara.telemetry.client import derive_anonymous_id, get_installation


class TestInstallationTableSingleton:
    """US1: Verify the migration creates exactly one installation row."""

    @pytest.mark.asyncio
    async def test_installation_table_has_exactly_one_row(self, test_db_session: AsyncSession) -> None:
        """After migration, the installation table should contain exactly one row."""
        result = await test_db_session.exec(select(func.count()).select_from(Installation))
        count = result.one()
        assert count == 1

    @pytest.mark.asyncio
    async def test_installation_row_has_valid_uuid(self, test_db_session: AsyncSession) -> None:
        """The singleton row should have a valid UUID id."""
        result = await test_db_session.exec(select(Installation))
        installation = result.one()
        assert isinstance(installation.id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_installation_row_has_created_at(self, test_db_session: AsyncSession) -> None:
        """The singleton row should have a non-null created_at timestamp."""
        result = await test_db_session.exec(select(Installation))
        installation = result.one()
        assert installation.created_at is not None

    @pytest.mark.asyncio
    async def test_inserting_second_row_is_rejected(self, test_db_session: AsyncSession) -> None:
        """The singleton constraint should prevent inserting a second row."""
        second = Installation(id=uuid.uuid4(), salt=uuid.uuid4())
        test_db_session.add(second)
        with pytest.raises(IntegrityError):
            await test_db_session.flush()
        await test_db_session.rollback()

    @pytest.mark.asyncio
    async def test_get_installation_returns_record(self, test_db_session: AsyncSession) -> None:
        """get_installation() should return the Installation record from the database."""
        installation = await get_installation(test_db_session)
        assert installation is not None
        assert isinstance(installation.id, uuid.UUID)
        assert isinstance(installation.salt, uuid.UUID)


class TestDeriveAnonymousId:
    """US2: Verify anonymous ID derivation from installation ID and DB coordinates."""

    def test_deterministic_same_inputs(self) -> None:
        """Same inputs should always produce the same anonymous ID."""
        installation_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result1 = derive_anonymous_id(installation_id, "db.example.com", "syntara_prod")
        result2 = derive_anonymous_id(installation_id, "db.example.com", "syntara_prod")
        assert result1 == result2

    def test_output_is_64_char_hex_string(self) -> None:
        """The anonymous ID should be a 64-character hex string (SHA-256)."""
        installation_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        result = derive_anonymous_id(installation_id, "localhost", "syntara")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
