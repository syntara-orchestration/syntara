"""Identity Provider Service for database operations and business logic."""

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

import structlog
from sqlalchemy import Select, exists, text
from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.auth.exceptions import GroupNotFoundError
from syntara.auth.session import create_session_store
from syntara.core.models import User, UserIdentity
from syntara.core.models.group import Group, user_groups, user_idp_groups
from syntara.core.services import BaseService
from syntara.core.services.secret_consumer_mixin import SecretConsumerMixin
from syntara.core.services.secret_service import SecretService
from syntara.core.utils.filters import Filter
from syntara.identity_providers.audit.identity_provider import IdentityProviderLifecycleEvent
from syntara.identity_providers.exceptions import (
    IdentityProviderError,
    IdentityProviderNameConflictError,
    IdentityProviderNotFoundError,
)
from syntara.identity_providers.models.identity_provider import (
    IdentityProvider,
    IdentityProviderCreate,
    IdentityProviderListResponse,
    IdentityProviderRead,
    IdentityProviderUpdate,
)
from syntara.identity_providers.models.identity_provider_configuration import (
    IdentityProviderConfigurationUpdateTypes,
    OIDCConfiguration,
    OIDCConfigurationResponse,
    OIDCConfigurationUpdate,
    OIDCGroupMappingEntry,
    OIDCIdpType,
)
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry

SelectIdentityProvider = Select[tuple[IdentityProvider]] | SelectOfScalar[tuple[IdentityProvider]]

logger = structlog.stdlib.get_logger(__name__)


class IdentityProviderService(BaseService, SecretConsumerMixin):
    """Service for Identity Provider CRUD operations and business logic."""

    def __init__(self, session: AsyncSession, user: User, secret_service: SecretService) -> None:
        """Initialize service with database session, current user, and secret service."""
        super().__init__(session, user)
        self._secret_service = secret_service

    def _is_duplicate_name_error(self, e: IntegrityError) -> bool:
        """Check if IntegrityError is due to duplicate provider name."""
        error_str = str(e)
        return (
            "ix_identity_providers_name_unique" in error_str
            or "identity_providers.name" in error_str
            or ("duplicate key" in error_str.lower() and "name" in error_str.lower())
        )

    async def _handle_integrity_error(self, e: IntegrityError, provider_name: str) -> NoReturn:
        """Handle IntegrityError and raise appropriate domain exception."""
        if self._is_duplicate_name_error(e):
            raise IdentityProviderNameConflictError(provider_name) from e
        raise e

    def _get_special_field_handlers(self) -> dict[str, Any]:
        """Get special field handlers for identity provider specific filtering."""

        def handle_provider_type(
            query: SelectIdentityProvider, filter_obj: Filter, _model: type[IdentityProvider]
        ) -> SelectIdentityProvider:
            if filter_obj.operator.value == "eq":
                return query.filter(text("configuration->>'provider_type' = :value")).params(value=filter_obj.value)
            return query

        return {
            "provider_type": handle_provider_type,
            "configuration.provider_type": handle_provider_type,
        }

    async def list_providers(
        self,
        limit: int = 100,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
    ) -> IdentityProviderListResponse:
        """List identity providers with filtering, sorting, and pagination."""
        special_field_handlers = self._get_special_field_handlers()

        return await self.list_resources(
            model=IdentityProvider,
            response_type=IdentityProviderListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            special_field_handlers=special_field_handlers,
            query_params_items=query_params_items,
            include_total=include_total,
        )

    async def get_provider(self, provider_id: UUID) -> IdentityProviderRead:
        """Get an identity provider by ID."""
        query = select(IdentityProvider).filter(
            IdentityProvider.id == provider_id,  # type: ignore[arg-type]
        )

        result = await self.session.exec(query)
        provider = result.one_or_none()

        if not provider:
            msg = f"Identity provider {provider_id} not found"
            raise IdentityProviderNotFoundError(msg)

        response = IdentityProviderRead.model_validate(provider)
        return await self._populate_response_entries(response)

    @staticmethod
    def _extract_group_mapping_entries(
        configuration: OIDCConfiguration | IdentityProviderConfigurationUpdateTypes,
    ) -> list[OIDCGroupMappingEntry]:
        """Extract mapping entries to be saved in the dedicated DB table."""
        entries = configuration.group_mapping_entries
        if entries is None or len(entries) == 0:
            return []
        return list(entries)

    async def _save_group_mapping_entries(
        self,
        provider_id: UUID,
        entries: list[OIDCGroupMappingEntry],
    ) -> None:
        """Insert group mapping entries into the DB table.

        Raises:
            GroupNotFoundError: If any nexus_group_id does not exist or is soft-deleted.

        """
        if entries:
            requested_ids = {e.nexus_group_id for e in entries}
            result = await self.session.exec(
                select(Group.id).where(
                    col(Group.id).in_(requested_ids),
                    Group.deleted_at.is_(None),  # type: ignore[union-attr]
                )
            )
            found_ids = set(result.all())
            missing = requested_ids - found_ids
            if missing:
                raise GroupNotFoundError(next(iter(missing)))

        for entry in entries:
            row = IdpGroupMappingEntry(
                identity_provider_id=provider_id,
                idp_group_value=entry.idp_group_value,
                nexus_group_id=entry.nexus_group_id,
            )
            self.session.add(row)

    async def _replace_group_mapping_entries(
        self,
        provider_id: UUID,
        entries: list[OIDCGroupMappingEntry],
    ) -> None:
        """Delete existing entries for provider and insert new ones."""
        await self.session.exec(
            sa_delete(IdpGroupMappingEntry).where(col(IdpGroupMappingEntry.identity_provider_id) == provider_id)
        )
        await self._save_group_mapping_entries(provider_id, entries)

    async def _load_group_mapping_entries(self, provider_id: UUID) -> list[OIDCGroupMappingEntry]:
        """Load group mapping entries from DB for a provider."""
        result = await self.session.exec(
            select(IdpGroupMappingEntry).where(IdpGroupMappingEntry.identity_provider_id == provider_id)
        )
        return [
            OIDCGroupMappingEntry(
                idp_group_value=row.idp_group_value,
                nexus_group_id=row.nexus_group_id,
            )
            for row in result.all()
        ]

    async def _populate_response_entries(
        self,
        response: IdentityProviderRead,
    ) -> IdentityProviderRead:
        """Populate group_mapping_entries on a response from the DB table."""
        config = response.configuration
        if isinstance(config, (OIDCConfiguration, OIDCConfigurationResponse)):
            config.group_mapping_entries = await self._load_group_mapping_entries(response.id)
        return response

    async def create_provider(self, provider_create: IdentityProviderCreate) -> IdentityProviderRead:
        """Create a new identity provider."""
        # Extract entries for the dedicated table before splitting config
        entries: list[OIDCGroupMappingEntry] = []
        if isinstance(provider_create.configuration, OIDCConfiguration):
            entries = self._extract_group_mapping_entries(provider_create.configuration)

        # Encrypt sensitive fields via SecretService (splits client_secret out of JSONB)
        safe_config, secret_id = await self._store_config(provider_create.configuration)

        provider = IdentityProvider(
            name=provider_create.name,
            description=provider_create.description,
            configuration=safe_config,
            secret_id=secret_id,
            enabled=True,
            created_by=self.user.id,
            updated_by=self.user.id,
        )

        self.session.add(provider)

        try:
            await self.session.flush()
            if entries:
                await self._save_group_mapping_entries(provider.id, entries)
            await self.session.commit()
            logger.info("Successfully created identity provider", provider_name=provider.name)
            AuditEventDispatcher.dispatch(
                IdentityProviderLifecycleEvent(
                    provider_id=provider.id,
                    provider_name=provider.name,
                    action="created",
                    disable_tls_verify=getattr(provider_create.configuration, "disable_tls_verify", False),
                ),
            )
            response = IdentityProviderRead.model_validate(provider)
            return await self._populate_response_entries(response)

        except IntegrityError as e:
            await self._handle_integrity_error(e, provider_create.name)

    async def _apply_configuration_patch(
        self,
        provider: IdentityProvider,
        patch_config: IdentityProviderConfigurationUpdateTypes,
        *,
        group_mapping_provided: bool,
    ) -> list[OIDCGroupMappingEntry] | None:
        """Apply configuration patch, preserving unset fields.

        Returns extracted group mapping entries when group_mapping was explicitly
        provided, or None to leave the entries table untouched.
        """
        # Preserve existing claim_mapping if not provided in patch
        if patch_config.claim_mapping is None:
            patch_config.claim_mapping = provider.configuration.claim_mapping
        # Preserve existing group_jmespath_expression if not provided in patch
        if patch_config.group_jmespath_expression is None:
            patch_config.group_jmespath_expression = provider.configuration.group_jmespath_expression
        # Preserve existing allow_all_authenticated if not provided in patch
        if patch_config.allow_all_authenticated is None:
            patch_config.allow_all_authenticated = provider.configuration.allow_all_authenticated
        # Preserve existing aap_role_mapping_enabled if not provided in patch
        if patch_config.aap_role_mapping_enabled is None:
            patch_config.aap_role_mapping_enabled = provider.configuration.aap_role_mapping_enabled
        # Preserve existing disable_tls_verify if not provided in patch
        if patch_config.disable_tls_verify is None:
            patch_config.disable_tls_verify = provider.configuration.disable_tls_verify

        if (
            isinstance(patch_config, OIDCConfigurationUpdate)
            and patch_config.aap_role_mapping_enabled
            and patch_config.idp_type != OIDCIdpType.AAP
        ):
            msg = "aap_role_mapping_enabled requires idp_type to be 'aap'"
            raise IdentityProviderError(msg)

        # Encrypt/preserve client_secret via SecretService
        safe_config, new_secret_id = await self._update_config(patch_config, provider.secret_id)
        provider.secret_id = new_secret_id

        # Only extract/replace entries when group_mapping_entries was explicitly provided
        patch_entries: list[OIDCGroupMappingEntry] | None = None
        if group_mapping_provided:
            patch_entries = self._extract_group_mapping_entries(patch_config)

        provider.configuration = safe_config  # type: ignore[assignment]
        return patch_entries

    async def update_provider(self, provider_id: UUID, provider_patch: IdentityProviderUpdate) -> IdentityProviderRead:
        """Patch an identity provider."""
        query = select(IdentityProvider).filter(
            IdentityProvider.id == provider_id,  # type: ignore[arg-type]
        )

        result = await self.session.exec(query)
        provider = result.one_or_none()

        if not provider:
            msg = f"Identity provider {provider_id} not found"
            raise IdentityProviderNotFoundError(msg)

        provider_name = provider_patch.name if provider_patch.name is not None else provider.name

        if provider_patch.name is not None:
            provider.name = provider_patch.name

        if provider_patch.description is not None:
            provider.description = provider_patch.description

        if provider_patch.enabled is not None:
            provider.enabled = provider_patch.enabled

        patch_entries: list[OIDCGroupMappingEntry] | None = None
        if provider_patch.configuration is not None:
            # Detect whether group_mapping_entries was explicitly provided before preservation logic runs
            group_mapping_provided = provider_patch.configuration.group_mapping_entries is not None
            patch_entries = await self._apply_configuration_patch(
                provider,
                provider_patch.configuration,
                group_mapping_provided=group_mapping_provided,
            )

        provider.updated_by = self.user.id
        provider.updated_at = datetime.now(UTC)

        try:
            await self.session.flush()
            if patch_entries is not None:
                await self._replace_group_mapping_entries(provider.id, patch_entries)
            await self.session.commit()
            AuditEventDispatcher.dispatch(
                IdentityProviderLifecycleEvent(
                    provider_id=provider.id,
                    provider_name=provider_name,
                    action="updated",
                    disable_tls_verify=getattr(provider.configuration, "disable_tls_verify", False),
                ),
            )
            return await self.get_provider(provider.id)

        except IntegrityError as e:
            await self._handle_integrity_error(e, provider_name)

    async def get_decrypted_config(self, provider: IdentityProvider) -> OIDCConfiguration:
        """Load provider configuration with decrypted secrets for internal use (e.g. OIDC token exchange)."""
        config_data = provider.configuration.model_dump()
        return await self._load_config(OIDCConfiguration, config_data, provider.secret_id)  # type: ignore[return-value]

    async def delete_provider(self, provider_id: UUID) -> None:
        """Hard delete an identity provider and clean up linked identities and sessions."""
        query = select(IdentityProvider).filter(
            IdentityProvider.id == provider_id,  # type: ignore[arg-type]
        )

        result = await self.session.exec(query)
        provider = result.one_or_none()

        if not provider:
            msg = f"Identity provider {provider_id} not found"
            raise IdentityProviderNotFoundError(msg)

        # Bulk-delete all user identities linked to this provider
        delete_result = await self.session.exec(
            sa_delete(UserIdentity).where(col(UserIdentity.identity_provider_id) == provider_id)
        )
        deleted_count = delete_result.rowcount
        if deleted_count:
            logger.info(
                "Deleted user identities for removed provider",
                provider_id=str(provider_id),
                count=deleted_count,
            )

        # Clean up IdP group memberships for this provider (2 queries total).
        # 1. Remove user_groups rows whose sole IdP source was this provider.
        #    Scoped to affected users via subquery; EXISTS/NOT EXISTS keeps
        #    memberships that are also tracked by another provider.
        affected_users_sq = (
            select(user_idp_groups.c.user_id).where(user_idp_groups.c.identity_provider_id == provider_id).distinct()
        )
        memberships_result = await self.session.exec(
            sa_delete(user_groups).where(
                user_groups.c.user_id.in_(affected_users_sq),
                exists().where(
                    user_idp_groups.c.user_id == user_groups.c.user_id,
                    user_idp_groups.c.group_id == user_groups.c.group_id,
                    user_idp_groups.c.identity_provider_id == provider_id,
                ),
                ~exists().where(
                    user_idp_groups.c.user_id == user_groups.c.user_id,
                    user_idp_groups.c.group_id == user_groups.c.group_id,
                    user_idp_groups.c.identity_provider_id != provider_id,
                ),
            )
        )
        memberships_removed = memberships_result.rowcount

        # 2. Delete all tracking rows for this provider.
        tracking_result = await self.session.exec(
            sa_delete(user_idp_groups).where(
                user_idp_groups.c.identity_provider_id == provider_id,
            )
        )
        tracking_deleted = tracking_result.rowcount

        if tracking_deleted:
            logger.info(
                "Cleaned up IdP group memberships for deleted provider",
                provider_id=str(provider_id),
                tracking_rows=tracking_deleted,
                memberships_removed=memberships_removed,
            )

        # Revoke all sessions authenticated via this provider (indexed by ID)
        store = create_session_store(self.session)
        revoked = await store.revoke_by_idp(str(provider_id))
        if revoked > 0:
            logger.info("Revoked sessions for deleted provider", provider=provider.name, count=revoked)

        # Capture for audit event before delete invalidates the instance
        provider_id = provider.id
        provider_name = provider.name

        # Delete encrypted secrets — null FK first to avoid constraint violation
        secret_id = provider.secret_id
        provider.secret_id = None
        self.session.add(provider)
        await self.session.flush()

        if secret_id:
            await self._secret_service.delete_secret(secret_id)

        await self.session.delete(provider)
        await self.session.commit()

        AuditEventDispatcher.dispatch(
            IdentityProviderLifecycleEvent(
                provider_id=provider_id,
                provider_name=provider_name,
                action="deleted",
            )
        )
