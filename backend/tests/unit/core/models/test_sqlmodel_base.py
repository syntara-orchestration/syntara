"""Contract tests for SQLModel base classes.

These tests verify that the SQLModel base classes can be imported and have the
expected structure, with labels as Dict[str, str] and proper inheritance.
These tests will initially fail until the SQLModel classes are implemented.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from syntara.core.models.base import (
    BaseResource,
    NamedResource,
    Resource,
    SoftDeletableResource,
    UserOwnedResource,
)
from syntara.core.models.pagination import ResourcesResponse, ResourcesResponseBase
from tests.unit.core.models.mock_shared_resources import MockBaseResource, MockNamedResource, MockResource


class TestSQLModelBaseClasses:
    """Test SQLModel base class structure and behavior."""

    def test_base_resource_import_and_structure(self) -> None:
        """Test that BaseResource can be imported and has expected fields."""
        # This will fail until BaseResource is implemented

        # Test field types and annotations
        annotations = BaseResource.__annotations__
        assert annotations["id"] == UUID
        assert annotations["created_at"] == datetime
        assert annotations["updated_at"] == datetime
        assert annotations["labels"] == dict[str, str]

    def test_base_resource_sqlmodel_table_config(self) -> None:
        """Test that BaseResource is configured as abstract SQLModel."""
        # BaseResource should be abstract (table=False)
        # Concrete classes should have table=True

        assert hasattr(MockBaseResource, "__table__")

    def test_base_resource_instance_creation(self) -> None:
        """Test MockBaseResource instance creation with labels."""
        resource_id = uuid4()
        now = datetime.now(UTC)
        labels = {"environment": "production", "region": "us-east-1"}

        # Create instance using concrete mock class
        resource = MockBaseResource(id=resource_id, created_at=now, updated_at=now, labels=labels)

        assert resource.id == resource_id
        assert resource.created_at == now
        assert resource.updated_at == now
        assert resource.labels == labels
        assert isinstance(resource.labels, dict)

    def test_base_resource_labels_validation(self) -> None:
        """Test that labels field validates as Dict[str, str]."""
        resource_id = uuid4()
        now = datetime.now(UTC)

        # Valid labels
        valid_resource = MockBaseResource(
            id=resource_id, created_at=now, updated_at=now, labels={"key1": "value1", "key2": "value2"}
        )
        assert valid_resource.labels == {"key1": "value1", "key2": "value2"}

        # Labels default to empty dict when not provided
        default_resource = MockBaseResource(id=resource_id, created_at=now, updated_at=now)
        assert default_resource.labels == {}

        # Invalid labels should raise ValidationError. Invalid: value must be string
        with pytest.raises(ValidationError):
            MockBaseResource(
                id=resource_id,
                created_at=now,
                updated_at=now,
                labels={"key": 123},
            )

    def test_named_resource_inheritance(self) -> None:
        """Test that NamedResource inherits from BaseResource."""
        assert issubclass(NamedResource, BaseResource)

        # Check additional fields
        annotations = NamedResource.__annotations__
        assert annotations["name"] is str
        assert annotations["description"] == str | None

    def test_named_resource_instance_creation(self) -> None:
        """Test MockNamedResource instance creation."""
        resource_id = uuid4()
        now = datetime.now(UTC)

        resource = MockNamedResource(
            id=resource_id,
            created_at=now,
            updated_at=now,
            labels={"environment": "test"},
            name="Test Resource",
            description="A test resource",
        )

        # Has BaseResource fields
        assert resource.id == resource_id
        assert resource.labels == {"environment": "test"}

        # Has NamedResource fields
        assert resource.name == "Test Resource"
        assert resource.description == "A test resource"

    def test_soft_deletable_resource_inheritance(self) -> None:
        """Test that SoftDeletableResource inherits from BaseResource."""
        assert issubclass(SoftDeletableResource, BaseResource)

        # Check additional fields
        annotations = SoftDeletableResource.__annotations__
        assert annotations["deleted_at"] == datetime | None
        assert annotations["deleted_by"] == UUID | None

    def test_user_owned_resource_inheritance(self) -> None:
        """Test that UserOwnedResource inherits from BaseResource."""
        assert issubclass(UserOwnedResource, BaseResource)

        # Check additional fields
        annotations = UserOwnedResource.__annotations__
        assert annotations["created_by"] == UUID
        assert annotations["updated_by"] == UUID | None

    def test_resource_multiple_inheritance(self) -> None:
        """Test that Resource combines all base capabilities."""
        # Resource should inherit from all three
        assert issubclass(Resource, NamedResource)
        assert issubclass(Resource, SoftDeletableResource)
        assert issubclass(Resource, UserOwnedResource)

    def test_resource_complete_instance(self) -> None:
        """Test MockResource instance with all fields."""
        resource_id = uuid4()
        user_id = uuid4()
        now = datetime.now(UTC)

        resource = MockResource(
            # BaseResource fields
            id=resource_id,
            created_at=now,
            updated_at=now,
            labels={"environment": "production", "team": "platform"},
            # NamedResource fields
            name="Production API",
            description="Main production API service",
            # SoftDeletableResource fields
            deleted_at=None,
            deleted_by=None,
            # UserOwnedResource fields
            created_by=user_id,
            updated_by=user_id,
        )

        # Verify all field groups
        assert resource.id == resource_id
        assert resource.labels == {"environment": "production", "team": "platform"}
        assert resource.name == "Production API"
        assert resource.description == "Main production API service"
        assert resource.deleted_at is None
        assert resource.deleted_by is None
        assert resource.created_by == user_id
        assert resource.updated_by == user_id

    def test_pagination_models_structure(self) -> None:
        """Test pagination response models."""
        # Test base pagination metadata
        base_response = ResourcesResponseBase(next="https://api.example.com/resources?cursor=abc", prev=None, total=100)

        assert base_response.next == "https://api.example.com/resources?cursor=abc"
        assert base_response.prev is None
        assert base_response.total == 100

        # Test full resources response

        resources_response = ResourcesResponse[MockResource](
            resources=[], next="https://api.example.com/resources?cursor=abc", prev=None, total=100
        )

        assert isinstance(resources_response.resources, list)
        assert resources_response.next == "https://api.example.com/resources?cursor=abc"
