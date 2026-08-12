"""Tests for SecretConsumerMixin — config store/update/load/mask operations."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from syntara.core.lib.consumer_configuration import BaseConsumerConfiguration
from syntara.core.lib.encryption import ENCRYPTED_SENTINEL
from syntara.core.services.secret_consumer_mixin import SecretConsumerMixin

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _TestConfig(BaseConsumerConfiguration):
    """Concrete config for testing."""

    provider_type: str = "test"
    client_id: str
    client_secret: str
    endpoint: str = "https://example.com"

    @classmethod
    def sensitive_fields(cls) -> frozenset[str]:
        return frozenset({"client_secret"})


class _TestService(SecretConsumerMixin):
    """Concrete service for testing the mixin."""

    def __init__(self, secret_service: AsyncMock) -> None:
        self._secret_service = secret_service


@pytest.fixture
def mock_secret_service() -> AsyncMock:
    """Create a mock SecretService with default return values."""
    svc = AsyncMock()
    svc.create_secret = AsyncMock(return_value=uuid4())
    svc.retrieve_secret = AsyncMock(return_value={"client_secret": "decrypted-value"})
    svc.update_secret = AsyncMock()
    svc.delete_secret = AsyncMock()
    return svc


@pytest.fixture
def service(mock_secret_service: AsyncMock) -> _TestService:
    """Create a test service wrapping the mock."""
    return _TestService(mock_secret_service)


# ---------------------------------------------------------------------------
# _store_config tests
# ---------------------------------------------------------------------------


class TestStoreConfig:
    """Tests for _store_config."""

    @pytest.mark.anyio
    async def test_extracts_sensitive_fields_and_stores(
        self, service: _TestService, mock_secret_service: AsyncMock
    ) -> None:
        config = _TestConfig(client_id="id-1", client_secret="my-secret")  # noqa: S106
        safe_dict, secret_id = await service._store_config(config)

        assert "client_secret" not in safe_dict
        assert safe_dict["client_id"] == "id-1"
        assert safe_dict["provider_type"] == "test"
        assert safe_dict["endpoint"] == "https://example.com"
        assert secret_id is not None
        mock_secret_service.create_secret.assert_awaited_once_with({"client_secret": "my-secret"})

    @pytest.mark.anyio
    async def test_returns_none_secret_id_when_no_sensitive_values(
        self, service: _TestService, mock_secret_service: AsyncMock
    ) -> None:
        class _PublicConfig(BaseConsumerConfiguration):
            name: str

        config = _PublicConfig(name="test")
        safe_dict, secret_id = await service._store_config(config)

        assert secret_id is None
        assert safe_dict == {"name": "test"}
        mock_secret_service.create_secret.assert_not_awaited()

    @pytest.mark.anyio
    async def test_rejects_unknown_sensitive_field_names(
        self,
        service: _TestService,
    ) -> None:
        """Typo in sensitive_fields() raises TypeError at store time."""

        class _BadConfig(BaseConsumerConfiguration):
            client_id: str
            client_secret: str

            @classmethod
            def sensitive_fields(cls) -> frozenset[str]:
                return frozenset({"clinet_secret"})  # typo

        config = _BadConfig(client_id="id", client_secret="secret")  # noqa: S106
        with pytest.raises(TypeError, match="unknown fields"):
            await service._store_config(config)


# ---------------------------------------------------------------------------
# _update_config tests
# ---------------------------------------------------------------------------


class TestUpdateConfig:
    """Tests for _update_config."""

    @pytest.mark.anyio
    async def test_preserves_existing_secret_on_sentinel(
        self, service: _TestService, mock_secret_service: AsyncMock
    ) -> None:
        existing_id = uuid4()

        config = _TestConfig(client_id="id-1", client_secret=ENCRYPTED_SENTINEL)
        safe_dict, secret_id = await service._update_config(config, existing_id)

        assert secret_id == existing_id
        assert "client_secret" not in safe_dict
        # No retrieve or update needed — all sentinels means no changes
        mock_secret_service.retrieve_secret.assert_not_awaited()
        mock_secret_service.update_secret.assert_not_awaited()

    @pytest.mark.anyio
    async def test_replaces_secret_with_new_value(self, service: _TestService, mock_secret_service: AsyncMock) -> None:
        existing_id = uuid4()
        mock_secret_service.retrieve_secret.return_value = {"client_secret": "old-secret"}

        config = _TestConfig(client_id="id-1", client_secret="new-secret")  # noqa: S106
        _safe_dict, secret_id = await service._update_config(config, existing_id)

        assert secret_id == existing_id
        mock_secret_service.update_secret.assert_awaited_once_with(existing_id, {"client_secret": "new-secret"})

    @pytest.mark.anyio
    async def test_creates_new_secret_when_none_exists(
        self, service: _TestService, mock_secret_service: AsyncMock
    ) -> None:
        config = _TestConfig(client_id="id-1", client_secret="brand-new")  # noqa: S106
        _safe_dict, secret_id = await service._update_config(config, None)

        assert secret_id is not None
        mock_secret_service.create_secret.assert_awaited_once_with({"client_secret": "brand-new"})

    @pytest.mark.anyio
    async def test_returns_none_when_no_secret_and_sentinel(
        self, service: _TestService, mock_secret_service: AsyncMock
    ) -> None:
        config = _TestConfig(client_id="id-1", client_secret=ENCRYPTED_SENTINEL)
        _safe_dict, secret_id = await service._update_config(config, None)

        assert secret_id is None
        mock_secret_service.create_secret.assert_not_awaited()

    @pytest.mark.anyio
    async def test_partial_update_with_multiple_sensitive_fields(self, mock_secret_service: AsyncMock) -> None:
        """Update one sensitive field while preserving another via sentinel."""

        class _MultiSecretConfig(BaseConsumerConfiguration):
            endpoint: str
            client_secret: str
            api_key: str

            @classmethod
            def sensitive_fields(cls) -> frozenset[str]:
                return frozenset({"client_secret", "api_key"})

        service = _TestService(mock_secret_service)
        existing_id = uuid4()
        mock_secret_service.retrieve_secret.return_value = {
            "client_secret": "old-secret",
            "api_key": "old-api-key",
        }

        config = _MultiSecretConfig(
            endpoint="https://example.com",
            client_secret="new-secret",  # noqa: S106
            api_key=ENCRYPTED_SENTINEL,  # preserve existing
        )
        safe_dict, secret_id = await service._update_config(config, existing_id)

        assert secret_id == existing_id
        assert "client_secret" not in safe_dict
        assert "api_key" not in safe_dict
        assert safe_dict["endpoint"] == "https://example.com"
        mock_secret_service.update_secret.assert_awaited_once_with(
            existing_id,
            {"client_secret": "new-secret", "api_key": "old-api-key"},
        )


# ---------------------------------------------------------------------------
# _load_config tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for _load_config."""

    @pytest.mark.anyio
    async def test_merges_stored_and_decrypted(self, service: _TestService, mock_secret_service: AsyncMock) -> None:
        secret_id = uuid4()
        stored = {"provider_type": "test", "client_id": "id-1", "endpoint": "https://example.com"}
        mock_secret_service.retrieve_secret.return_value = {"client_secret": "decrypted"}

        result = await service._load_config(_TestConfig, stored, secret_id)

        assert isinstance(result, _TestConfig)
        assert result.client_id == "id-1"
        assert result.client_secret == "decrypted"  # noqa: S105
        mock_secret_service.retrieve_secret.assert_awaited_once_with(secret_id)

    @pytest.mark.anyio
    async def test_loads_without_secret_id(self, service: _TestService, mock_secret_service: AsyncMock) -> None:
        class _PublicConfig(BaseConsumerConfiguration):
            label: str

        stored = {"label": "test"}
        result = await service._load_config(_PublicConfig, stored, None)

        assert result.model_dump()["label"] == "test"
        mock_secret_service.retrieve_secret.assert_not_awaited()


# ---------------------------------------------------------------------------
# _mask_config tests
# ---------------------------------------------------------------------------


class TestMaskConfig:
    """Tests for _mask_config (static method)."""

    def test_replaces_sensitive_with_sentinel(self) -> None:
        secret_id = uuid4()
        stored = {
            "provider_type": "test",
            "client_id": "id-1",
            "client_secret": "real",
            "endpoint": "https://example.com",
        }
        masked = SecretConsumerMixin._mask_config(_TestConfig, stored, secret_id)

        assert masked["client_secret"] == ENCRYPTED_SENTINEL
        assert masked["client_id"] == "id-1"
        assert masked["provider_type"] == "test"

    def test_omits_sensitive_when_no_secret(self) -> None:
        stored = {"provider_type": "test", "client_id": "id-1"}
        masked = SecretConsumerMixin._mask_config(_TestConfig, stored, None)

        assert "client_secret" not in masked

    def test_does_not_inject_sentinel_for_unstored_fields(self) -> None:
        """Sensitive fields not present in stored_config should not appear as $encrypted$."""
        secret_id = uuid4()
        stored = {"provider_type": "test", "client_id": "id-1", "endpoint": "https://example.com"}
        masked = SecretConsumerMixin._mask_config(_TestConfig, stored, secret_id)

        assert "client_secret" not in masked
        assert masked["client_id"] == "id-1"

    def test_preserves_non_sensitive_fields(self) -> None:
        secret_id = uuid4()
        stored = {"provider_type": "test", "client_id": "id-1", "endpoint": "https://custom.com"}
        masked = SecretConsumerMixin._mask_config(_TestConfig, stored, secret_id)

        assert masked["endpoint"] == "https://custom.com"
