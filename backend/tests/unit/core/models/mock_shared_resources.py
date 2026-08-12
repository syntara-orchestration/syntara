"""Mock concrete implementations of shared resource models for testing."""

from syntara.core.models.base import BaseResource, NamedResource, Resource


class MockBaseResource(BaseResource, table=True):
    """Concrete implementation of BaseResource for testing."""

    __tablename__ = "mock_base_resources"


class MockNamedResource(NamedResource, table=True):
    """Concrete implementation of NamedResource for testing."""

    __tablename__ = "mock_named_resources"


class MockResource(Resource, table=True):
    """Concrete implementation of Resource for testing."""

    __tablename__ = "mock_resources"
