"""Tests for BaseConsumerConfiguration."""

import pytest
from pydantic import ValidationError

from syntara.core.lib.consumer_configuration import BaseConsumerConfiguration


class _TestConfig(BaseConsumerConfiguration):
    """Concrete subclass for testing."""

    client_id: str
    client_secret: str
    endpoint: str = "https://example.com"

    @classmethod
    def sensitive_fields(cls) -> frozenset[str]:
        return frozenset({"client_secret"})


class TestSensitiveFields:
    """Tests for the sensitive_fields() classmethod."""

    def test_base_class_returns_empty_frozenset(self) -> None:
        assert BaseConsumerConfiguration.sensitive_fields() == frozenset()

    def test_subclass_overrides_sensitive_fields(self) -> None:
        assert _TestConfig.sensitive_fields() == frozenset({"client_secret"})

    def test_sensitive_fields_is_frozenset(self) -> None:
        result = _TestConfig.sensitive_fields()
        assert isinstance(result, frozenset)


class TestExtraForbid:
    """Tests for extra='forbid' configuration."""

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            _TestConfig(client_id="id", client_secret="secret", unknown_field="bad")  # noqa: S106

    def test_accepts_valid_fields(self) -> None:
        config = _TestConfig(client_id="id", client_secret="secret")  # noqa: S106
        assert config.client_id == "id"
        assert config.client_secret == "secret"  # noqa: S105
        assert config.endpoint == "https://example.com"


class TestModelDump:
    """Tests for model_dump() behaviour."""

    def test_dumps_all_fields(self) -> None:
        config = _TestConfig(client_id="id", client_secret="secret")  # noqa: S106
        dumped = config.model_dump()
        assert dumped == {
            "client_id": "id",
            "client_secret": "secret",
            "endpoint": "https://example.com",
        }

    def test_dumps_with_custom_endpoint(self) -> None:
        config = _TestConfig(client_id="id", client_secret="s", endpoint="https://other.com")  # noqa: S106
        dumped = config.model_dump()
        assert dumped["endpoint"] == "https://other.com"


class TestNoSensitiveFieldsSubclass:
    """Tests for subclass that has no sensitive fields."""

    def test_empty_sensitive_fields(self) -> None:
        with pytest.warns(UserWarning, match="does not override sensitive_fields"):

            class _PublicConfig(BaseConsumerConfiguration):
                name: str
                url: str

        assert _PublicConfig.sensitive_fields() == frozenset()
        config = _PublicConfig(name="test", url="https://example.com")
        assert config.model_dump() == {"name": "test", "url": "https://example.com"}
