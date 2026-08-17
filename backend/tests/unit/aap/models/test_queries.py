"""Tests for AAP query parameter models.

Validates that AAPBaseQuery and AAPResourceQuery accept the integration_id field.
"""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.aap.models.queries import AAPBaseQuery, AAPResourceQuery


class TestAAPBaseQueryIntegrationId:
    """Verify integration_id on AAPBaseQuery."""

    def test_accepts_valid_uuid(self) -> None:
        """integration_id should accept a valid UUID."""
        uid = uuid4()
        query = AAPBaseQuery(integration_id=uid)
        assert query.integration_id == uid

    def test_accepts_uuid_from_string(self) -> None:
        """integration_id should accept a UUID parsed from string."""
        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        query = AAPBaseQuery(integration_id=uuid_str)  # type: ignore[arg-type]
        assert query.integration_id == UUID(uuid_str)

    def test_defaults_to_none(self) -> None:
        """integration_id should default to None when not provided."""
        query = AAPBaseQuery()
        assert query.integration_id is None

    def test_rejects_invalid_uuid_string(self) -> None:
        """integration_id should reject non-UUID strings."""
        with pytest.raises(ValidationError):
            AAPBaseQuery(integration_id="not-a-uuid")  # type: ignore[arg-type]

    def test_coexists_with_credential_id(self) -> None:
        """integration_id and credential_id can be set simultaneously."""
        integration_uid = uuid4()
        credential_uid = uuid4()
        query = AAPBaseQuery(integration_id=integration_uid, credential_id=credential_uid)
        assert query.integration_id == integration_uid
        assert query.credential_id == credential_uid


class TestAAPResourceQueryIntegrationId:
    """Verify integration_id inherited by AAPResourceQuery."""

    def test_accepts_valid_uuid(self) -> None:
        """AAPResourceQuery should accept integration_id (inherited from AAPBaseQuery)."""
        uid = uuid4()
        query = AAPResourceQuery(integration_id=uid)
        assert query.integration_id == uid

    def test_defaults_to_none(self) -> None:
        """integration_id should default to None on AAPResourceQuery."""
        query = AAPResourceQuery()
        assert query.integration_id is None

    def test_coexists_with_organization_filter(self) -> None:
        """integration_id can be used alongside the organization filter."""
        uid = uuid4()
        query = AAPResourceQuery(integration_id=uid, organization="Engineering")
        assert query.integration_id == uid
        assert query.organization == "Engineering"
