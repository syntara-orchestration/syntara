"""Unit tests for service account credential API schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.service_accounts.credential_schemas import (
    SACredentialCreate,
    SACredentialCreateResponse,
    SACredentialListParams,
    SACredentialListResponse,
    SACredentialRead,
    SACredentialRotateRequest,
    SACredentialRotateResponse,
)
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredentialStatus,
    ServiceAccountCredentialType,
)


class TestSACredentialCreate:
    """Tests for SACredentialCreate schema validation."""

    def test_valid_create_client_credentials(self) -> None:
        data = SACredentialCreate(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS)
        assert data.credential_type == ServiceAccountCredentialType.CLIENT_CREDENTIALS
        assert data.grace_period_seconds == 3600

    def test_credential_type_required(self) -> None:
        with pytest.raises(ValidationError, match="credential_type"):
            SACredentialCreate()

    def test_grace_period_optional(self) -> None:
        data = SACredentialCreate(
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            grace_period_seconds=7200,
        )
        assert data.grace_period_seconds == 7200

    def test_grace_period_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            SACredentialCreate(
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                grace_period_seconds=-1,
            )

    def test_grace_period_rejects_over_24h(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 86400"):
            SACredentialCreate(
                credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
                grace_period_seconds=86401,
            )


class TestSACredentialRead:
    """Tests for SACredentialRead response schema."""

    def test_from_attributes(self) -> None:
        now = datetime.now(tz=UTC)
        cred_id = uuid4()
        sa_id = uuid4()
        user_id = uuid4()
        data = SACredentialRead(
            id=cred_id,
            service_account_id=sa_id,
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            status=ServiceAccountCredentialStatus.ACTIVE,
            grace_period_seconds=3600,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        assert data.id == cred_id
        assert data.service_account_id == sa_id
        assert data.identifier == "nx_sa_abcdef1234567890"
        assert data.expires_at is None
        assert data.last_used_at is None

    def test_no_secret_field(self) -> None:
        assert "hashed_secret" not in SACredentialRead.model_fields
        assert "client_secret" not in SACredentialRead.model_fields


class TestSACredentialCreateResponse:
    """Tests for SACredentialCreateResponse — includes one-time secrets."""

    def test_includes_client_secret(self) -> None:
        now = datetime.now(tz=UTC)
        data = SACredentialCreateResponse(
            id=uuid4(),
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            status=ServiceAccountCredentialStatus.ACTIVE,
            grace_period_seconds=3600,
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
            client_secret="the-secret-value",  # noqa: S106
        )
        assert data.client_secret == "the-secret-value"  # noqa: S105

    def test_client_secret_optional(self) -> None:
        now = datetime.now(tz=UTC)
        data = SACredentialCreateResponse(
            id=uuid4(),
            service_account_id=uuid4(),
            credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS,
            identifier="nx_sa_abcdef1234567890",
            status=ServiceAccountCredentialStatus.ACTIVE,
            grace_period_seconds=3600,
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        assert data.client_secret is None


class TestSACredentialRotateRequest:
    """Tests for SACredentialRotateRequest schema."""

    def test_grace_period_optional(self) -> None:
        data = SACredentialRotateRequest()
        assert data.grace_period_seconds is None

    def test_grace_period_override(self) -> None:
        data = SACredentialRotateRequest(grace_period_seconds=7200)
        assert data.grace_period_seconds == 7200


class TestSACredentialRotateResponse:
    """Tests for SACredentialRotateResponse schema."""

    def test_inherits_create_response(self) -> None:
        assert issubclass(SACredentialRotateResponse, SACredentialCreateResponse)


class TestSACredentialListParams:
    """Tests for list query parameters."""

    def test_defaults(self) -> None:
        params = SACredentialListParams()
        assert params.limit == 20
        assert params.cursor is None
        assert params.credential_type is None
        assert params.status is None

    def test_credential_type_filter(self) -> None:
        params = SACredentialListParams(credential_type=ServiceAccountCredentialType.CLIENT_CREDENTIALS)
        assert params.credential_type == ServiceAccountCredentialType.CLIENT_CREDENTIALS


class TestSACredentialListResponse:
    """Tests for paginated list response."""

    def test_empty_response(self) -> None:
        response = SACredentialListResponse(resources=[], next=None, prev=None)
        assert response.resources == []
        assert response.total is None
