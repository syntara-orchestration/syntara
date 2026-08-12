"""Unit tests for service account API schemas."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from syntara.service_accounts.models.service_account import ServiceAccountStatus
from syntara.service_accounts.schemas import (
    ServiceAccountCreate,
    ServiceAccountListParams,
    ServiceAccountListResponse,
    ServiceAccountRead,
    ServiceAccountUpdate,
)


class TestServiceAccountCreate:
    """Tests for ServiceAccountCreate schema validation."""

    def test_valid_create(self) -> None:
        data = ServiceAccountCreate(
            name="CI Pipeline",
            description="Used by CI/CD",
            project_id=uuid4(),
        )
        assert data.name == "CI Pipeline"
        assert data.description == "Used by CI/CD"

    def test_name_required(self) -> None:
        with pytest.raises(ValidationError, match="name"):
            ServiceAccountCreate(project_id=uuid4())

    def test_project_id_required(self) -> None:
        with pytest.raises(ValidationError, match="project_id"):
            ServiceAccountCreate(name="test")

    def test_description_optional(self) -> None:
        data = ServiceAccountCreate(name="test", project_id=uuid4())
        assert data.description is None

    def test_name_min_length(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            ServiceAccountCreate(name="", project_id=uuid4())

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ServiceAccountCreate(name="x" * 256, project_id=uuid4())

    def test_description_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ServiceAccountCreate(name="test", description="x" * 2001, project_id=uuid4())


class TestServiceAccountUpdate:
    """Tests for ServiceAccountUpdate schema validation."""

    def test_all_fields_optional(self) -> None:
        data = ServiceAccountUpdate()
        assert data.name is None
        assert data.description is None

    def test_partial_update_name_only(self) -> None:
        data = ServiceAccountUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.description is None

    def test_partial_update_description_only(self) -> None:
        data = ServiceAccountUpdate(description="New desc")
        assert data.description == "New desc"
        assert data.name is None

    def test_name_min_length(self) -> None:
        with pytest.raises(ValidationError, match="at least 1"):
            ServiceAccountUpdate(name="")


class TestServiceAccountRead:
    """Tests for ServiceAccountRead response schema."""

    def test_from_attributes(self) -> None:
        now = datetime.now(tz=UTC)
        sa_id = uuid4()
        user_id = uuid4()
        project_id = uuid4()
        data = ServiceAccountRead(
            id=sa_id,
            name="test",
            status=ServiceAccountStatus.ACTIVE,
            project_id=project_id,
            created_by=user_id,
            created_at=now,
            updated_at=now,
        )
        assert data.id == sa_id
        assert data.name == "test"
        assert data.status == ServiceAccountStatus.ACTIVE
        assert data.description is None
        assert data.last_authenticated_at is None
        assert data.updated_by is None
        assert data.labels == {}

    def test_no_secret_field(self) -> None:
        assert "client_secret" not in ServiceAccountRead.model_fields
        assert "hashed_secret" not in ServiceAccountRead.model_fields

    def test_no_client_id_field(self) -> None:
        assert "client_id" not in ServiceAccountRead.model_fields


class TestServiceAccountListParams:
    """Tests for list query parameters."""

    def test_defaults(self) -> None:
        params = ServiceAccountListParams()
        assert params.limit == 20
        assert params.cursor is None
        assert params.sort is None
        assert params.include_total is False
        assert params.status is None
        assert params.name is None

    def test_status_filter(self) -> None:
        params = ServiceAccountListParams(status=ServiceAccountStatus.DISABLED)
        assert params.status == ServiceAccountStatus.DISABLED


class TestServiceAccountListResponse:
    """Tests for paginated list response."""

    def test_empty_response(self) -> None:
        response = ServiceAccountListResponse(resources=[], next=None, prev=None)
        assert response.resources == []
        assert response.next is None
        assert response.prev is None
        assert response.total is None
