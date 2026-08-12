"""Mixin for domain services that store configuration with sensitive fields.

Provides four methods for storing, updating, loading, and masking
configuration objects with encrypted sensitive fields via SecretService.

NOT used by CredentialService (dynamic schemas with type-defined fields).
Used by IdentityProviderService and future consumers with static schemas.
"""

from typing import Any
from uuid import UUID

import structlog

from syntara.core.lib.consumer_configuration import BaseConsumerConfiguration
from syntara.core.lib.encryption import ENCRYPTED_SENTINEL
from syntara.core.services.secret_service import SecretService

logger = structlog.stdlib.get_logger(__name__)


def _split_sensitive(
    config: BaseConsumerConfiguration,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a config into (safe_fields, sensitive_fields) dicts.

    Validates that all declared sensitive field names exist in the model.
    """
    sensitive_keys = config.sensitive_fields()
    all_fields = config.model_dump()
    unknown = sensitive_keys - all_fields.keys()
    if unknown:
        msg = f"{type(config).__name__}.sensitive_fields() declares unknown fields: {unknown}"
        raise TypeError(msg)
    safe = {k: v for k, v in all_fields.items() if k not in sensitive_keys}
    secret = {k: v for k, v in all_fields.items() if k in sensitive_keys and v is not None}
    return safe, secret


def _real_updates(fields: dict[str, Any]) -> dict[str, Any]:
    """Filter out sentinel and None values, keeping only real updates."""
    return {k: v for k, v in fields.items() if v is not None and v != ENCRYPTED_SENTINEL}


class SecretConsumerMixin:
    """Mixin for services managing models with BaseConsumerConfiguration.

    Consuming classes must set self._secret_service before calling these methods.
    Callers are responsible for persisting the returned secret_id on their domain model.

    Usage pattern::

        class MyService(SecretConsumerMixin):
            async def create(self, data):
                safe, secret_id = await self._store_config(my_config)
                # persist row with configuration=safe, secret_id=secret_id

            async def get_for_internal_use(self, row):
                return await self._load_config(MyConfig, row.configuration, row.secret_id)

            def to_api_response(self, row):
                return self._mask_config(MyConfig, row.configuration, row.secret_id)

    """

    _secret_service: SecretService

    async def _store_config(
        self,
        config: BaseConsumerConfiguration,
    ) -> tuple[dict[str, Any], UUID | None]:
        """Extract sensitive fields, encrypt via SecretService, return sanitised config.

        Returns:
            Tuple of (safe_config_dict, secret_id). secret_id is None if
            the config has no sensitive fields with non-None values.

        """
        safe, secret = _split_sensitive(config)

        if not secret:
            return safe, None

        logger.debug("Storing config secrets", config_type=type(config).__name__, field_count=len(secret))
        secret_id = await self._secret_service.create_secret(secret)
        logger.info("Stored config secrets", secret_id=str(secret_id))
        return safe, secret_id

    async def _update_config(
        self,
        config: BaseConsumerConfiguration,
        existing_secret_id: UUID | None,
    ) -> tuple[dict[str, Any], UUID | None]:
        """Sentinel-aware update: preserve existing secrets where value is ENCRYPTED_SENTINEL.

        Returns:
            Tuple of (safe_config_dict, secret_id).

        """
        safe, new_secrets = _split_sensitive(config)
        updates = _real_updates(new_secrets)

        if existing_secret_id:
            if not updates:
                return safe, existing_secret_id
            logger.debug(
                "Merging secret updates", secret_id=str(existing_secret_id), updated_fields=list(updates.keys())
            )
            existing = await self._secret_service.retrieve_secret(existing_secret_id)
            await self._secret_service.update_secret(existing_secret_id, {**existing, **updates})
            return safe, existing_secret_id

        if not updates:
            return safe, None

        secret_id = await self._secret_service.create_secret(updates)
        return safe, secret_id

    async def _load_config(
        self,
        config_type: type[BaseConsumerConfiguration],
        stored_config: dict[str, Any],
        secret_id: UUID | None,
    ) -> BaseConsumerConfiguration:
        """Reconstruct full typed config from JSONB + decrypted secrets.

        Use when real secret values are needed (building auth requests,
        resolving credentials). Never use on API response path.

        """
        data = dict(stored_config)
        if secret_id:
            data.update(await self._secret_service.retrieve_secret(secret_id))
        try:
            return config_type.model_validate(data)
        except Exception:
            logger.exception(
                "Configuration validation failed after secret merge",
                config_type=config_type.__name__,
                secret_id=str(secret_id),
                stored_fields=list(stored_config.keys()),
            )
            raise

    @staticmethod
    def _mask_config(
        config_type: type[BaseConsumerConfiguration],
        stored_config: dict[str, Any],
        secret_id: UUID | None,
    ) -> dict[str, Any]:
        """Replace sensitive field values with ENCRYPTED_SENTINEL for API responses.

        Does NOT contact SecretService or require decryption.

        """
        masked = dict(stored_config)
        if secret_id is not None:
            for field_name in config_type.sensitive_fields():
                if field_name in stored_config:
                    masked[field_name] = ENCRYPTED_SENTINEL
        return masked
