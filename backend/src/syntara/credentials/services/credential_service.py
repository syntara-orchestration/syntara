"""Credential Service for database operations and business logic.

Handles CRUD operations with encryption/decryption delegated to SecretService
and secret masking in API responses.
"""

import json
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime
from uuid import UUID

import structlog
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_ssh_private_key
from sqlalchemy import Select, case, func, literal_column, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql._expression_select_cls import SelectOfScalar

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.authz.engine import AllowedProjectsResult
from syntara.core.config.base import get_settings
from syntara.core.exceptions import assert_project_id_unchanged
from syntara.core.lib.encryption import ENCRYPTED_SENTINEL, EncryptionError
from syntara.core.lib.sanitization import CONTROL_CHAR_MULTILINE_RE, CONTROL_CHAR_SINGLELINE_RE
from syntara.core.lib.url_validation import validate_host_url
from syntara.core.models import User
from syntara.core.services import BaseService
from syntara.core.services.extensions import ConvertResourceMixin, EnrichQueryMixin
from syntara.core.services.secret_service import SecretService
from syntara.credentials.audit.credential import CredentialEncryptionFailureEvent, CredentialLifecycleEvent
from syntara.credentials.exceptions import (
    CredentialDecryptionError,
    CredentialInUseError,
    CredentialNameConflictError,
    CredentialNotFoundError,
    CredentialValidationError,
)
from syntara.credentials.models.credential import (
    Credential,
    CredentialCreate,
    CredentialListResponse,
    CredentialRead,
    CredentialUpdate,
    CredentialWorkflowRef,
)
from syntara.credentials.models.credential_type import CredentialType
from syntara.integrations.models.integration import Integration

logger = structlog.stdlib.get_logger(__name__)


MAX_INPUTS_SIZE_BYTES = 65536  # 64KB max for serialized inputs payload


def _get_secret_field_ids(type_inputs: dict[str, Any]) -> set[str]:
    """Extract the set of field IDs marked as secret from a credential type's inputs schema."""
    fields = type_inputs.get("fields", [])
    return {f["id"] for f in fields if f.get("secret", False)}


_SSH_KEY_ENCRYPTED_MSG = "SSH private key is passphrase-protected. Only unprotected keys are supported."


def _validate_ssh_private_key(value: str) -> None:
    """Reject passphrase-protected or malformed SSH private keys."""
    data = value.encode("utf-8")
    try:
        load_ssh_private_key(data, password=None)
        return
    except (TypeError, UnsupportedAlgorithm):
        raise CredentialValidationError(_SSH_KEY_ENCRYPTED_MSG) from None
    except ValueError:
        pass

    try:
        load_pem_private_key(data, password=None)
        return
    except TypeError:
        raise CredentialValidationError(_SSH_KEY_ENCRYPTED_MSG) from None
    except (ValueError, UnsupportedAlgorithm):
        msg = "Invalid SSH private key format."
        raise CredentialValidationError(msg) from None


def _validate_field_value(field_id: str, value: Any, field_def: dict[str, Any]) -> None:  # noqa: ANN401
    """Validate a single field value against its schema definition."""
    choices = field_def.get("choices")
    if choices and value not in choices:
        msg = f"Invalid value '{value}' for field '{field_id}'. Must be one of: {', '.join(choices)}"
        raise CredentialValidationError(msg)

    if field_def.get("type") == "boolean" and not isinstance(value, bool):
        msg = f"Field '{field_id}' must be a boolean (true/false), got {type(value).__name__}"
        raise CredentialValidationError(msg)

    if field_def.get("type") == "string" and not isinstance(value, str):
        msg = f"Field '{field_id}' must be a string, got {type(value).__name__}"
        raise CredentialValidationError(msg)

    if field_id == "ssh_private_key":
        _validate_ssh_private_key(value)

    if field_id == "host":
        if not isinstance(value, str):
            msg = f"Field 'host' must be a string, got {type(value).__name__}"
            raise CredentialValidationError(msg)
        try:
            validate_host_url(value, allow_http=get_settings().credential_allow_http_host)
        except ValueError as e:
            msg = f"Invalid host URL: {e} Provide only scheme and hostname, e.g., https://controller.example.com"
            raise CredentialValidationError(msg) from None

    if isinstance(value, str):
        pattern = CONTROL_CHAR_MULTILINE_RE if field_def.get("multiline") else CONTROL_CHAR_SINGLELINE_RE
        if pattern.search(value):
            msg = f"Field '{field_id}' contains a control character. Remove control characters and try again."
            raise CredentialValidationError(msg)


def _validate_field_constraints(inputs: dict[str, Any], type_inputs: dict[str, Any]) -> None:
    """Enforce inter-field constraints: mutually_exclusive, required_one_of, required_together.

    Schema keys (all optional, declared in type_inputs):
        mutually_exclusive: list[list[str]] — groups that cannot be populated simultaneously.
            A group is "populated" when ALL of its fields are present and non-empty.
            (Note: False and 0 count as populated — only None, "", and absent are excluded.)
        required_one_of: list[list[str]] — at least one of these groups must be populated.
        required_together: list[list[str]] — if any field in a sublist is provided,
            all others in that sublist must also be provided.

    Raises:
        CredentialValidationError: On constraint violation.

    """
    _missing = object()

    def _is_provided(field: str) -> bool:
        # Sentinel-based: treats False/0 as provided, but not None/""/absent
        return inputs.get(field, _missing) not in (_missing, None, "")

    def _group_is_populated(group: list[str]) -> bool:
        return bool(group) and all(_is_provided(f) for f in group)

    # required_together: if any field in a group is provided, all must be
    for group in type_inputs.get("required_together", []):
        provided_in_group = [f for f in group if _is_provided(f)]
        if provided_in_group and len(provided_in_group) != len(group):
            missing = [f for f in group if not _is_provided(f)]
            msg = f"Fields must be provided together: {', '.join(group)}. Missing: {', '.join(missing)}"
            raise CredentialValidationError(msg)

    # mutually_exclusive: no two groups can be populated at the same time
    exclusive_groups: list[list[str]] = type_inputs.get("mutually_exclusive", [])
    if exclusive_groups:
        populated = [g for g in exclusive_groups if _group_is_populated(g)]
        if len(populated) > 1:
            labels = [" + ".join(g) for g in populated]
            msg = f"These field groups are mutually exclusive: {' and '.join(labels)}"
            raise CredentialValidationError(msg)

    # required_one_of: at least one group must be fully populated
    required_one_of: list[list[str]] = type_inputs.get("required_one_of", [])
    if required_one_of and not any(_group_is_populated(g) for g in required_one_of):
        labels = [" + ".join(g) for g in required_one_of]
        msg = f"At least one field group required: {' or '.join(labels)}"
        raise CredentialValidationError(msg)


def _validate_inputs(
    inputs: dict[str, Any],
    type_inputs: dict[str, Any],
    *,
    allow_sentinel: bool = False,
) -> None:
    """Validate credential inputs against the type schema.

    Args:
        inputs: User-provided field values.
        type_inputs: CredentialType.inputs schema with fields and required arrays.
        allow_sentinel: If True, $encrypted$ values are allowed (for PATCH updates).

    Raises:
        CredentialValidationError: If validation fails.

    """
    fields = type_inputs.get("fields", [])
    field_defs = {f["id"]: f for f in fields}
    required = set(type_inputs.get("required", []))
    valid_ids = set(field_defs.keys())

    serialized_size = len(json.dumps(inputs).encode("utf-8"))
    if serialized_size > MAX_INPUTS_SIZE_BYTES:
        msg = f"Inputs payload exceeds maximum size of {MAX_INPUTS_SIZE_BYTES} bytes ({serialized_size} bytes)"
        raise CredentialValidationError(msg)

    # Reject unknown field IDs
    unknown = set(inputs.keys()) - valid_ids
    if unknown:
        msg = f"Unknown field(s): {', '.join(sorted(unknown))}"
        raise CredentialValidationError(msg)

    # Reject $encrypted$ sentinel on create (reserved for PATCH masking)
    if not allow_sentinel:
        sentinel_fields = [k for k, v in inputs.items() if v == ENCRYPTED_SENTINEL]
        if sentinel_fields:
            msg = (
                f"The value '$encrypted$' is reserved and cannot be used as input "
                f"for field(s): {', '.join(sentinel_fields)}"
            )
            raise CredentialValidationError(msg)

    # Check required fields — only on create (PATCH is partial, missing fields are preserved)
    if not allow_sentinel:
        provided = {k for k, v in inputs.items() if v is not None}
        missing = required - provided
        if missing:
            msg = f"Missing required field(s): {', '.join(sorted(missing))}"
            raise CredentialValidationError(msg)

    # Enforce inter-field constraints (mutually_exclusive, required_one_of, required_together)
    if not allow_sentinel:
        _validate_field_constraints(inputs, type_inputs)

    # Validate choices, types, and format
    for field_id, value in inputs.items():
        if value is None or value == ENCRYPTED_SENTINEL:
            continue
        field_def = field_defs.get(field_id, {})
        _validate_field_value(field_id, value, field_def)


class CredentialEnrichQuery(EnrichQueryMixin):
    """Eager-load credential type relationship."""

    def enrich(  # type: ignore[override]
        self,
        query: Select[tuple[Credential]] | SelectOfScalar[tuple[Credential]],
    ) -> Select[tuple[Credential]] | SelectOfScalar[tuple[Credential]]:
        """Extend query to eager load credential type."""
        return query.options(selectinload(Credential.credential_type))  # type: ignore[arg-type]


class CredentialConvertResource(ConvertResourceMixin):
    """Convert Credential to CredentialRead with secret masking for list responses."""

    def __init__(self, credential_type_cache: dict[UUID, CredentialType]) -> None:
        """Initialize with type cache for masking lookups."""
        self._type_cache = credential_type_cache

    def convert_resource(self, resource: Credential) -> CredentialRead:  # type: ignore[override]
        """Convert Credential to read schema with all fields masked as $encrypted$."""
        read = CredentialRead.model_validate(resource)
        credential_type = self._type_cache.get(resource.credential_type_id) or resource.credential_type
        if credential_type:
            read.inputs = _mask_all_secrets(credential_type.inputs)
        return read


def _mask_all_secrets(type_inputs: dict[str, Any]) -> dict[str, Any]:
    """Mask all fields with $encrypted$ sentinel for list responses (no decryption)."""
    fields = type_inputs.get("fields", [])
    return {f["id"]: ENCRYPTED_SENTINEL for f in fields}


def _extract_credential_node_names(workflow_definition: dict[str, Any], credential_id: str) -> list[str]:
    """Extract node names from a V2 workflow definition that reference a given credential."""
    return [
        node.get("name") or node.get("id", "Unknown")
        for node in workflow_definition.get("nodes", [])
        if _get_node_credential_id(node) == credential_id
    ]


def _get_node_credential_id(node: dict[str, Any]) -> str | None:
    parameters: dict[str, Any] = node.get("parameters", {})
    result: str | None = parameters.get("credential_id")
    return result


class CredentialService(BaseService):
    """Service for Credential CRUD operations with encryption via SecretService."""

    def __init__(self, session: AsyncSession, user: User, secret_service: SecretService) -> None:
        """Initialize with database session, user context, and SecretService."""
        self._secret_service = secret_service
        self._type_cache: dict[UUID, CredentialType] = {}
        super().__init__(
            session,
            user,
            enrich_query_mixin=CredentialEnrichQuery(),
            convert_resource_mixin=CredentialConvertResource(self._type_cache),
        )

    async def _get_credential_type(self, credential_type_id: UUID) -> CredentialType:
        """Fetch and cache a credential type by ID."""
        if credential_type_id in self._type_cache:
            return self._type_cache[credential_type_id]
        result = await self.session.get(CredentialType, credential_type_id)
        if not result:
            msg = f"Credential type with ID '{credential_type_id}' not found"
            raise CredentialNotFoundError(msg)
        self._type_cache[credential_type_id] = result
        return result

    def _build_masked_response(
        self,
        credential: Credential,
        credential_type: CredentialType,
        decrypted_inputs: dict[str, Any],
    ) -> CredentialRead:
        """Build a CredentialRead with selective masking — secret fields masked, non-secret in plaintext."""
        secret_field_ids = _get_secret_field_ids(credential_type.inputs)
        read = CredentialRead.model_validate(credential)
        read.inputs = {
            field_id: (ENCRYPTED_SENTINEL if field_id in secret_field_ids else value)
            for field_id, value in decrypted_inputs.items()
        }
        return read

    async def _lookup_users(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> dict[str | UUID, tuple[UUID, str]] | None:
        """Collect user UUIDs from *objects* and batch-resolve them.

        Returns a mapping {uuid: (uuid, username)} on success, or
        None when the lookup query fails (caller decides fallback).
        """
        user_ids: set[str | UUID] = set()
        for obj in objects:
            for field in field_names:
                val = getattr(obj, field, None)
                if val:
                    user_ids.add(val)
        if not user_ids:
            return {}
        try:
            stmt = select(User.id, User.username).where(User.id.in_(user_ids))  # type: ignore[attr-defined]
            result = await self.session.exec(stmt)
            return {row[0]: (row[0], row[1]) for row in result}
        except (SQLAlchemyError, OSError):
            logger.warning("Failed to resolve usernames", exc_info=True)
            return None

    async def _resolve_user_references(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> None:
        """Resolve user UUID fields to UserReference objects in-place.

        Unresolvable UUIDs (e.g. deleted users) produce None rather than
        an empty object, per AC-4 of AAP-79148.
        """
        from syntara.core.models.user_reference import UserReference  # noqa: PLC0415

        user_map = await self._lookup_users(objects, field_names)
        if user_map is None:
            for obj in objects:
                for field in field_names:
                    setattr(obj, field, None)
            return
        for obj in objects:
            for field in field_names:
                val = getattr(obj, field, None)
                if val is not None and val in user_map:
                    uid, username = user_map[val]
                    setattr(obj, field, UserReference(id=uid, name=username))
                elif val is not None:
                    setattr(obj, field, None)

    async def _resolve_user_fields(
        self,
        objects: Sequence[Any],
        field_names: Sequence[str] = ("created_by", "updated_by"),
    ) -> None:
        """Resolve user UUID fields to username strings in-place.

        Used by endpoints that still return plain-string user fields
        (e.g. CredentialWorkflowRef).
        """
        user_map = await self._lookup_users(objects, field_names)
        if user_map is None:
            return
        for obj in objects:
            for field in field_names:
                val = getattr(obj, field, None)
                if val and val in user_map:
                    _, username = user_map[val]
                    setattr(obj, field, username)

    async def create_credential(self, data: CredentialCreate) -> CredentialRead:
        """Create a new credential with encrypted inputs via SecretService."""
        from syntara.authz.models import Project  # noqa: PLC0415
        from syntara.core.queries.project_queries import assert_project_alive  # noqa: PLC0415

        await assert_project_alive(self.session, data.project_id)

        project = await self.session.get(Project, data.project_id)
        if project and project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"Cannot create credentials in built-in project '{project.name}'"
            raise BuiltinProtectionError(msg)

        credential_type = await self._get_credential_type(data.credential_type_id)

        # Validate inputs against type schema (always validate — empty dict may miss required fields)
        _validate_inputs(data.inputs, credential_type.inputs)

        existing = await self._find_by_name(data.name, data.project_id)
        if existing:
            raise CredentialNameConflictError(data.name)

        # Store inputs via SecretService
        secret_id: UUID | None = None
        if data.inputs:
            secret_id = await self._secret_service.create_secret(data.inputs)

        credential = Credential(
            name=data.name,
            description=data.description,
            credential_type_id=data.credential_type_id,
            secret_id=secret_id,
            labels=data.labels,
            project_id=data.project_id,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info("Credential created", credential_id=str(credential.id), name=credential.name)
        AuditEventDispatcher.dispatch(
            CredentialLifecycleEvent(
                credential_id=credential.id,
                credential_name=credential.name,
                credential_type_id=credential.credential_type_id,
                action="created",
                project_id=credential.project_id,
            ),
        )

        decrypted_inputs = data.inputs or {}
        read = self._build_masked_response(credential, credential_type, decrypted_inputs)
        await self._resolve_user_references([read])
        return read

    @staticmethod
    def _emit_decryption_failure(credential: Credential) -> None:
        AuditEventDispatcher.dispatch(
            CredentialEncryptionFailureEvent(
                credential_id=credential.id,
                credential_name=credential.name,
                operation="decrypt",
                error_type="CredentialDecryptionError",
            ),
        )

    async def get_credential_raw(self, credential_id: UUID) -> Credential:
        """Get the raw credential DB model without decryption or enrichment."""
        return await self._get_or_raise(credential_id)

    async def get_credential(self, credential_id: UUID) -> CredentialRead:
        """Get a credential with secret fields masked, non-secret fields decrypted."""
        credential = await self._get_or_raise(credential_id)
        credential_type = await self._get_credential_type(credential.credential_type_id)

        try:
            decrypted_inputs = await self._retrieve_or_empty(credential.secret_id)
        except CredentialDecryptionError:
            self._emit_decryption_failure(credential)
            raise
        read = self._build_masked_response(credential, credential_type, decrypted_inputs)

        wf_counts = await self.get_workflow_counts([credential_id])
        read.workflow_count = wf_counts.get(credential_id, 0)
        int_counts = await self.get_integration_counts([credential_id])
        read.integration_count = int_counts.get(credential_id, 0)
        await self._resolve_user_references([read])

        return read

    async def list_credentials(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort: str | None = None,
        query_params_items: Iterable[tuple[str, str]] | None = None,
        *,
        include_total: bool = False,
        allowed_projects: AllowedProjectsResult | None = None,
    ) -> CredentialListResponse:
        """List credentials with metadata only (no decryption, no backend contact)."""
        response = await self.list_resources(
            Credential,
            CredentialListResponse,
            limit=limit,
            cursor=cursor,
            sort=sort,
            query_params_items=query_params_items,
            include_total=include_total,
            allowed_projects=allowed_projects,
        )

        cred_ids = [r.id for r in response.resources]
        if cred_ids:
            workflow_counts = await self.get_workflow_counts(cred_ids)
            integration_counts = await self.get_integration_counts(cred_ids)
            for resource in response.resources:
                resource.workflow_count = workflow_counts.get(resource.id, 0)
                resource.integration_count = integration_counts.get(resource.id, 0)

        await self._resolve_user_references(response.resources)

        return response

    async def update_credential(self, credential_id: UUID, data: CredentialUpdate) -> CredentialRead:
        """Update a credential. $encrypted$ preserves existing encrypted values."""
        from syntara.authz.models import Project  # noqa: PLC0415

        credential = await self._get_or_raise(credential_id)

        project = await self.session.get(Project, credential.project_id)
        if project and project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"Cannot update credentials in built-in project '{project.name}'"
            raise BuiltinProtectionError(msg)

        assert_project_id_unchanged(credential.project_id, data.project_id)

        credential_type = await self._get_credential_type(credential.credential_type_id)

        enabled_changed = data.enabled is not None and data.enabled != credential.enabled

        if data.name is not None and data.name != credential.name:
            existing = await self._find_by_name(data.name, credential.project_id)
            if existing and existing.id != credential.id:
                raise CredentialNameConflictError(data.name)
            credential.name = data.name

        if data.description is not None:
            credential.description = data.description
        if data.enabled is not None:
            credential.enabled = data.enabled
        if data.labels is not None:
            credential.labels = data.labels

        # Validate inputs (allow $encrypted$ sentinel for PATCH preservation)
        if data.inputs is not None:
            _validate_inputs(data.inputs, credential_type.inputs, allow_sentinel=True)

        # Handle inputs update with $encrypted$ preservation via SecretService
        decrypted_inputs: dict[str, Any] = {}
        try:
            if data.inputs is not None:
                decrypted_inputs = await self._merge_inputs(credential, data.inputs)
                _validate_field_constraints(decrypted_inputs, credential_type.inputs)
                credential.secret_id = await self._store_inputs(credential, decrypted_inputs)
            else:
                decrypted_inputs = await self._retrieve_or_empty(credential.secret_id)
        except CredentialDecryptionError:
            self._emit_decryption_failure(credential)
            raise

        credential.updated_by = self.user.id
        self.session.add(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        logger.info("Credential updated", credential_id=str(credential.id))
        AuditEventDispatcher.dispatch(
            CredentialLifecycleEvent(
                credential_id=credential.id,
                credential_name=credential.name,
                credential_type_id=credential.credential_type_id,
                action="updated",
                project_id=credential.project_id,
                enabled_changed=enabled_changed,
            ),
        )
        read = self._build_masked_response(credential, credential_type, decrypted_inputs)

        workflow_counts = await self.get_workflow_counts([credential_id])
        read.workflow_count = workflow_counts.get(credential_id, 0)
        integration_counts = await self.get_integration_counts([credential_id])
        read.integration_count = integration_counts.get(credential_id, 0)

        await self._resolve_user_references([read])

        return read

    async def get_integration_counts(self, credential_ids: list[UUID]) -> dict[UUID, int]:
        """Count integrations using each credential as their management credential.

        Args:
            credential_ids: List of credential UUIDs to count for.

        Returns:
            Dict mapping credential_id -> integration count.

        """
        if not credential_ids:
            return {}

        try:
            stmt = (
                select(
                    Integration.management_credential_id,
                    func.count().label("cnt"),
                )
                .where(
                    Integration.management_credential_id.in_(credential_ids),  # type: ignore[union-attr]
                )
                .group_by(Integration.management_credential_id)  # type: ignore[arg-type]
            )

            result = await self.session.exec(stmt)
            rows: list[tuple[UUID, int]] = [(row[0], row[1]) for row in result.all() if row[0] is not None]
            return dict(rows)
        except (SQLAlchemyError, OSError):
            logger.warning(
                "Failed to retrieve integration counts; returning empty",
                credential_ids=[str(cid) for cid in credential_ids],
                exc_info=True,
            )
            return {}

    @staticmethod
    def _is_management_credential_fk_violation(exc: IntegrityError) -> bool:
        """Check whether *exc* was caused by the management_credential_id RESTRICT FK."""
        error_str = str(exc)
        return "integrations_management_credential_id_fkey" in error_str

    async def _get_referencing_integration_names(self, credential_id: UUID, *, limit: int) -> list[str]:
        """Fetch up to `limit` names of integrations using this credential as their management credential.

        Used to build an actionable message for CredentialInUseError. The
        total count comes separately from get_integration_counts.
        """
        stmt = (
            select(Integration.name)
            .where(Integration.management_credential_id == credential_id)
            .order_by(Integration.name)
            .limit(limit)
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    async def delete_credential(self, credential_id: UUID) -> None:
        """Delete a credential and its secret data atomically.

        Raises:
            CredentialInUseError: If the credential is still set as the
                management credential on one or more integrations. Deleting
                it out from under those integrations would silently break
                them — management_credential_id would be nulled with no
                signal that validation_status is now stale.
                The caller must detach the credential from all referencing
                integrations first.

                The upfront count-based check below has a TOCTOU race: an
                integration could be attached between that check and the
                delete below. The `integrations.management_credential_id`
                FK is `ON DELETE RESTRICT` (not `SET NULL`) specifically so
                the database itself rejects the delete in that case rather
                than silently nulling the reference; the `except
                IntegrityError` re-raises that as the same clean
                CredentialInUseError instead of a generic constraint-violation
                response.

        """
        from syntara.authz.models import Project  # noqa: PLC0415

        credential = await self._get_or_raise(credential_id)

        project = await self.session.get(Project, credential.project_id)
        if project and project.is_builtin:
            from syntara.authz.exceptions import BuiltinProtectionError  # noqa: PLC0415

            msg = f"Cannot delete credentials in built-in project '{project.name}'"
            raise BuiltinProtectionError(msg)

        int_counts = await self.get_integration_counts([credential_id])
        int_ref_count = int_counts.get(credential_id, 0)
        if int_ref_count:
            integration_names = await self._get_referencing_integration_names(credential_id, limit=5)
            raise CredentialInUseError(credential.name, integration_names, int_ref_count)

        wf_counts = await self.get_workflow_counts([credential_id])
        wf_ref_count = wf_counts.get(credential_id, 0)
        if wf_ref_count:
            logger.warning(
                "Deleting credential still referenced by workflows",
                credential_id=str(credential_id),
                credential_name=credential.name,
                affected_workflow_count=wf_ref_count,
            )

        cred_name = credential.name
        cred_type_id = credential.credential_type_id
        cred_project_id = credential.project_id
        secret_id = credential.secret_id

        # Atomic delete: all changes happen in SQLAlchemy's implicit transaction.
        # Order matters for FK constraints:
        #   1. NULL credential.secret_id (removes credentials → secrets FK ref)
        #   2. delete_secret() removes EncryptedSecret then Secret rows
        #   3. delete credential row
        #   4. commit() finalizes everything in one transaction
        credential.secret_id = None
        self.session.add(credential)
        await self.session.flush()

        if secret_id:
            await self._secret_service.delete_secret(secret_id)

        await self.session.delete(credential)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if not self._is_management_credential_fk_violation(exc):
                raise
            logger.warning(
                "Credential delete raced with a new integration reference",
                credential_id=str(credential_id),
                credential_name=cred_name,
                exc_info=exc,
            )
            int_counts = await self.get_integration_counts([credential_id])
            int_ref_count = int_counts.get(credential_id, 0)
            if not int_ref_count:
                raise
            integration_names = await self._get_referencing_integration_names(credential_id, limit=5)
            raise CredentialInUseError(cred_name, integration_names, int_ref_count) from exc
        logger.info("Credential deleted", credential_id=str(credential_id))
        AuditEventDispatcher.dispatch(
            CredentialLifecycleEvent(
                credential_id=credential_id,
                credential_name=cred_name,
                credential_type_id=cred_type_id,
                action="deleted",
                project_id=cred_project_id,
                affected_workflow_count=wf_ref_count,
                # Always 0: a non-zero integration ref count raises CredentialInUseError above.
                affected_integration_count=0,
            ),
        )

    async def get_credential_workflows(self, credential_id: UUID) -> list[CredentialWorkflowRef]:
        """Find workflows that reference a given credential in their definitions.

        Uses PostgreSQL jsonb_path_exists for precise matching of credential_id
        values in workflow definitions. Returns enriched workflow references
        including description, creator, node names, and latest execution info.

        Args:
            credential_id: UUID of the credential.

        Returns:
            List of enriched workflow references that use this credential.

        Raises:
            CredentialNotFoundError: If credential does not exist.

        """
        from syntara.workflows.models.execution import Execution  # noqa: PLC0415

        await self._get_or_raise(credential_id)

        rows = await self._query_workflows_by_credential_ids([credential_id])
        workflow_ids = [row[0] for row in rows]

        # Batch-fetch latest execution per workflow (enrichment — graceful on failure)
        exec_map: dict[UUID, tuple[datetime, str]] = {}
        if workflow_ids:
            try:
                latest_exec_stmt = (
                    select(
                        Execution.workflow_id,
                        Execution.created_at,
                        Execution.status,
                    )
                    .where(
                        Execution.workflow_id.in_(workflow_ids),  # type: ignore[attr-defined]
                        Execution.deleted_at.is_(None),  # type: ignore[union-attr]
                    )
                    .order_by(Execution.workflow_id, Execution.created_at.desc())  # type: ignore[arg-type, attr-defined]
                    .distinct(Execution.workflow_id)  # type: ignore[arg-type]
                )
                exec_result = await self.session.exec(latest_exec_stmt)
                for exec_row in exec_result.all():
                    exec_map[exec_row[0]] = (exec_row[1], exec_row[2])
            except (SQLAlchemyError, OSError):
                logger.warning(
                    "Failed to fetch execution info for credential workflows",
                    credential_id=str(credential_id),
                    workflow_count=len(workflow_ids),
                    exc_info=True,
                )

        cred_id_str = str(credential_id)
        refs = []
        for row in rows:
            try:
                node_names = _extract_credential_node_names(row[2], cred_id_str) if isinstance(row[2], dict) else []
            except (TypeError, AttributeError, KeyError):
                logger.warning(
                    "Failed to extract node names from workflow definition", workflow_id=str(row[0]), exc_info=True
                )
                node_names = []
            exec_info = exec_map.get(row[0])
            refs.append(
                CredentialWorkflowRef(
                    id=row[0],
                    name=row[1],
                    description=row[3],
                    created_by=row[4],
                    created_at=row[5],
                    node_names=node_names,
                    last_execution_at=exec_info[0] if exec_info else None,
                    last_execution_status=exec_info[1] if exec_info else None,
                ),
            )

        # Resolve created_by UUIDs to usernames
        await self._resolve_user_fields(refs, field_names=("created_by",))

        return refs

    @staticmethod
    def _latest_workflow_versions_subquery() -> Any:  # noqa: ANN401
        """Subquery returning (workflow_id, max_version) for non-deleted workflow versions."""
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415

        return (
            select(
                WorkflowVersion.workflow_id,
                func.max(WorkflowVersion.version).label("max_version"),
            )
            .where(WorkflowVersion.deleted_at.is_(None))  # type: ignore[union-attr]
            .group_by(WorkflowVersion.workflow_id)  # type: ignore[arg-type]
            .subquery()
        )

    async def get_workflow_counts(
        self, credential_ids: list[UUID], *, project_id: UUID | None = None
    ) -> dict[UUID, int]:
        """Count workflows referencing each credential in a single SQL query.

        Uses PostgreSQL jsonb_path_exists with SUM(CASE) to count per-credential
        in one query against the latest workflow versions.

        Args:
            credential_ids: List of credential UUIDs to count for.
            project_id: If provided, only count workflows in this project.

        Returns:
            Dict mapping credential_id -> workflow count.

        """
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415

        if not credential_ids:
            return {}

        latest_version = self._latest_workflow_versions_subquery()

        # Build SUM(CASE WHEN jsonb_path_exists(...) THEN 1 ELSE 0 END) per credential
        count_columns = [
            func.sum(
                case(
                    (
                        func.jsonb_path_exists(
                            WorkflowVersion.workflow_definition,
                            literal_column(f"'$.**.credential_id ? (@ == \"{cid}\")'::jsonpath"),
                        ),
                        1,
                    ),
                    else_=0,
                ),
            ).label(str(cid))
            for cid in credential_ids
        ]

        stmt = (
            select(*count_columns)
            .select_from(Workflow)
            .join(latest_version, Workflow.id == latest_version.c.workflow_id)
            .join(
                WorkflowVersion,
                (WorkflowVersion.workflow_id == latest_version.c.workflow_id)
                & (WorkflowVersion.version == latest_version.c.max_version),
            )
            .where(Workflow.deleted_at.is_(None))  # type: ignore[union-attr]
        )
        if project_id is not None:
            stmt = stmt.where(Workflow.project_id == project_id)

        result = await self.session.exec(stmt)
        row = result.one_or_none()

        counts: dict[UUID, int] = dict.fromkeys(credential_ids, 0)
        if row:
            # SQLAlchemy returns a scalar for single-column SELECT, tuple for multiple
            values = (row,) if len(credential_ids) == 1 else row
            for i, cid in enumerate(credential_ids):
                counts[cid] = int(values[i] or 0)

        return counts

    async def _query_workflows_by_credential_ids(
        self,
        credential_ids: list[UUID],
        *,
        project_id: UUID | None = None,
    ) -> Sequence[Any]:
        """Query latest workflow definitions that reference any of the given credential IDs.

        Uses PostgreSQL jsonb_path_exists for precise JSON-level matching,
        avoiding false positives from substring matches on UUIDs.

        Args:
            credential_ids: Credential UUIDs to filter by.
            project_id: If provided, only query workflows in this project.

        Returns:
            Sequence of (workflow_id, workflow_name, workflow_definition, description, created_by, created_at) rows.

        """
        from syntara.workflows.models.workflow import Workflow  # noqa: PLC0415
        from syntara.workflows.models.workflow_version import WorkflowVersion  # noqa: PLC0415

        latest_version = self._latest_workflow_versions_subquery()

        stmt = (
            select(  # type: ignore[call-overload]
                Workflow.id,
                Workflow.name,
                WorkflowVersion.workflow_definition,
                Workflow.description,
                Workflow.created_by,
                Workflow.created_at,
            )
            .join(latest_version, Workflow.id == latest_version.c.workflow_id)
            .join(
                WorkflowVersion,
                (WorkflowVersion.workflow_id == latest_version.c.workflow_id)
                & (WorkflowVersion.version == latest_version.c.max_version),
            )
            .where(Workflow.deleted_at.is_(None))  # type: ignore[union-attr]
        )

        # Use jsonb_path_exists for precise credential_id matching (PostgreSQL 12+)
        # literal_column with ::jsonpath cast avoids asyncpg VARCHAR type mismatch
        jsonpath_conditions = [
            func.jsonb_path_exists(
                WorkflowVersion.workflow_definition,
                literal_column(f"'$.**.credential_id ? (@ == \"{cid}\")'::jsonpath"),
            )
            for cid in credential_ids
        ]
        stmt = stmt.where(or_(*jsonpath_conditions))
        if project_id is not None:
            stmt = stmt.where(Workflow.project_id == project_id)

        result = await self.session.exec(stmt)
        return result.all()  # type: ignore[no-any-return]

    async def _merge_inputs(self, credential: Credential, new_inputs: dict[str, Any]) -> dict[str, Any]:
        """Merge new inputs with existing (preserving $encrypted$) without persisting.

        Returns the merged plaintext for validation before storage.
        """
        existing_inputs = await self._retrieve_or_empty(credential.secret_id)

        return {
            **existing_inputs,
            **{k: v for k, v in new_inputs.items() if v != ENCRYPTED_SENTINEL},
        }

    async def _store_inputs(self, credential: Credential, merged_inputs: dict[str, Any]) -> UUID:
        """Persist already-validated merged inputs to SecretService."""
        if credential.secret_id:
            await self._secret_service.update_secret(credential.secret_id, merged_inputs)
            return credential.secret_id
        return await self._secret_service.create_secret(merged_inputs)

    async def _get_or_raise(self, credential_id: UUID) -> Credential:
        """Get credential by ID or raise CredentialNotFoundError."""
        query = select(Credential).where(
            Credential.id == credential_id,
        )
        result = await self.session.exec(query)
        credential = result.one_or_none()
        if not credential:
            msg = f"Credential with ID '{credential_id}' not found"
            raise CredentialNotFoundError(msg)
        return credential

    async def _retrieve_or_empty(self, secret_id: UUID | None) -> dict[str, Any]:
        """Retrieve decrypted inputs or return empty dict. Wraps EncryptionError."""
        if not secret_id:
            return {}
        try:
            return await self._secret_service.retrieve_secret(secret_id)
        except EncryptionError as e:
            msg = "Failed to decrypt credential data"
            raise CredentialDecryptionError(msg) from e

    async def _find_by_name(self, name: str, project_id: UUID) -> Credential | None:
        """Find a credential by name within a project."""
        stmt = select(Credential).where(
            Credential.name == name,
            Credential.project_id == project_id,
        )
        result = await self.session.exec(stmt)
        return result.first()
