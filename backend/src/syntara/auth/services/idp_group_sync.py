"""IdP group sync service for OIDC login.

Handles syncing Nexus group memberships based on identity provider
group mapping configuration during OIDC authentication flows.
"""

from fnmatch import fnmatch
from typing import Any
from uuid import UUID

import jmespath
import structlog
from sqlalchemy import delete as sa_delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.authz.audit.group_membership import dispatch_membership_diff_events
from syntara.core.lib.sanitization import escape_control_chars
from syntara.core.models import Group, User, UserIdentity
from syntara.core.models.group import user_groups, user_idp_groups
from syntara.identity_providers.models.identity_provider_configuration import (
    OIDCConfiguration,
    OIDCIdpType,
)
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry

logger = structlog.stdlib.get_logger(__name__)


def extract_idp_group_values(
    jmespath_expr: str,
    raw_merged_claims: dict[str, Any],
    user_id: UUID,
) -> set[str] | None:
    """Extract group values from claims using JMESPath. Returns None on error."""
    logger.debug(
        "Evaluating JMESPath expression for group sync",
        expression=jmespath_expr,
        user_id=str(user_id),
    )
    try:
        raw_groups = jmespath.search(jmespath_expr, raw_merged_claims)
    except (ValueError, TypeError, jmespath.exceptions.JMESPathError):
        logger.warning("JMESPath expression failed during group sync", expression=jmespath_expr, user_id=str(user_id))
        return None

    if raw_groups is None and jmespath_expr.endswith("[*]"):
        base_expr = jmespath_expr.removesuffix("[*]")
        try:
            raw_value = jmespath.search(base_expr, raw_merged_claims)
        except (ValueError, TypeError, jmespath.exceptions.JMESPathError):
            raw_value = None
        if raw_value is not None and not isinstance(raw_value, (list, dict)):
            logger.error(
                "Groups claim is a scalar but JMESPath expression expects a list; "
                "either fix the IdP to send an array or remove the trailing [*] from the expression",
                expression=jmespath_expr,
                claim_type=type(raw_value).__name__,
                user_id=str(user_id),
            )
            return None

    if not isinstance(raw_groups, list):
        raw_groups = [raw_groups] if raw_groups else []
    return {escape_control_chars(str(g)) for g in raw_groups if g is not None}


def match_group_entries(
    mapping_entries: list[IdpGroupMappingEntry],
    idp_group_values: set[str],
) -> set[UUID]:
    """Match IdP group values against mapping entries, supporting glob wildcards.

    Entries can use ``*``, ``?``, and ``[seq]`` patterns (fnmatch syntax).
    For example, ``admin*`` matches ``admin-prod`` and ``admin-staging``.
    A bare ``*`` matches every group value.
    """
    desired: set[UUID] = set()
    for entry in mapping_entries:
        pattern = entry.idp_group_value
        if pattern == "*":
            logger.warning(
                "Wildcard '*' mapping matches all IdP groups — all provider users added to group",
                nexus_group_id=str(entry.nexus_group_id),
            )
            desired.add(entry.nexus_group_id)
            continue
        for value in idp_group_values:
            if fnmatch(value, pattern):
                desired.add(entry.nexus_group_id)
                break  # no need to check more values for this entry
    return desired


async def _resolve_aap_role_groups(
    db: AsyncSession,
    raw_merged_claims: dict[str, Any],
    user_id: UUID,
    config: OIDCConfiguration,
) -> set[UUID] | None:
    """Map AAP ``aap_system_role`` claim to built-in group IDs.

    Validates that the token's ``iss`` claim matches the configured
    ``issuer_url`` before trusting AAP-specific claims.  Returns ``None``
    on issuer mismatch to signal that login should be denied.  Normal
    users (no recognized system role) are assigned to the ``users`` group.
    """
    token_issuer = raw_merged_claims.get("iss")
    configured_issuer = str(config.issuer_url).rstrip("/")
    if not isinstance(token_issuer, str) or token_issuer.rstrip("/") != configured_issuer:
        logger.warning(
            "AAP role mapping denied: token issuer does not match configured issuer_url",
            token_issuer=token_issuer,
            expected_issuer=config.issuer_url,
            user_id=str(user_id),
        )
        return None

    role_to_group = {
        "system_administrator": "admins",
        "system_auditor": "auditors",
    }
    system_role = raw_merged_claims.get("aap_system_role")
    target_name = role_to_group.get(system_role) if isinstance(system_role, str) else None

    if not target_name:
        logger.debug(
            "AAP role mapping: normal user, assigning to users group",
            user_id=str(user_id),
            aap_system_role=system_role,
        )
        users_group_id = await _resolve_users_group(db, user_id)
        if users_group_id is None:
            return None
        return {users_group_id}

    result = await db.exec(
        select(Group).filter(
            col(Group.name) == target_name,
            col(Group.is_builtin) == True,  # noqa: E712
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    group = result.first()
    if not group:
        logger.error(
            "Built-in group not found for AAP role mapping",
            group_name=target_name,
            user_id=str(user_id),
        )
        return None

    logger.debug(
        "AAP role mapping resolved group",
        group_name=target_name,
        group_id=str(group.id),
        user_id=str(user_id),
        aap_system_role=system_role,
    )
    return {group.id}


_DEFAULT_JMESPATH_EXPRESSION = "groups[*]"


def _resolve_jmespath_expression(config: OIDCConfiguration) -> str:
    """Determine the JMESPath expression to use for group extraction."""
    return config.group_jmespath_expression or _DEFAULT_JMESPATH_EXPRESSION


def _resolve_claim_based_groups(
    user: User,
    raw_merged_claims: dict[str, Any],
    config: OIDCConfiguration,
    provider_id: UUID,
    mapping_entries: list[IdpGroupMappingEntry],
) -> set[UUID] | None:
    """Resolve groups from JMESPath and manual mapping. Returns None on extraction failure."""
    jmespath_expr = _resolve_jmespath_expression(config)
    idp_group_values = extract_idp_group_values(jmespath_expr, raw_merged_claims, user.id)
    if idp_group_values is None:
        logger.error(
            "JMESPath group extraction failed",
            expression=jmespath_expr,
            user_id=str(user.id),
            provider_id=str(provider_id),
        )
        return None

    return match_group_entries(mapping_entries, idp_group_values)


async def _resolve_users_group(db: AsyncSession, user_id: UUID) -> UUID | None:
    """Look up the built-in ``users`` group. Returns None if not found."""
    result = await db.exec(
        select(Group).filter(
            col(Group.name) == "users",
            col(Group.is_builtin) == True,  # noqa: E712
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    group: Group | None = result.first()
    if not group:
        logger.error("Built-in 'users' group not found", user_id=str(user_id))
        return None
    return group.id


async def _resolve_allow_all_groups(db: AsyncSession, user_id: UUID, config: OIDCConfiguration) -> set[UUID]:
    """Return the built-in ``users`` group if ``allow_all_authenticated`` is enabled."""
    if not config.allow_all_authenticated:
        return set()
    users_group_id = await _resolve_users_group(db, user_id)
    return {users_group_id} if users_group_id else set()


async def sync_idp_groups(
    db: AsyncSession,
    user: User,
    identity: UserIdentity,
    raw_merged_claims: dict[str, Any],
    config: OIDCConfiguration,
) -> bool:
    """Sync Nexus group memberships based on IdP group mapping.

    Session-scoped: clears all IdP-managed group memberships from every
    provider and replaces them with groups from the current login's token.
    Manually-assigned groups (those without ``user_idp_groups`` tracking
    rows) are never affected.

    Returns:
        True if at least one group was resolved from this provider.
        False if no groups were resolved — the caller should deny login
        unless the user has groups from other sources.

    """
    aap_role_mapping = config.aap_role_mapping_enabled and config.idp_type == OIDCIdpType.AAP
    provider_id = identity.identity_provider_id

    # Load mapping entries from DB table
    mapping_entries_result = await db.exec(
        select(IdpGroupMappingEntry).where(IdpGroupMappingEntry.identity_provider_id == provider_id)
    )
    mapping_entries = list(mapping_entries_result.all())

    has_claim_based = bool(mapping_entries)
    if not has_claim_based and not aap_role_mapping:
        desired = await _resolve_allow_all_groups(db, user.id, config)
        await _apply_group_membership_diff(db, user.id, provider_id, desired, username=user.username)
        return bool(desired)

    desired_group_ids = await _resolve_allow_all_groups(db, user.id, config)

    if has_claim_based:
        result = _resolve_claim_based_groups(user, raw_merged_claims, config, provider_id, mapping_entries)
        if result is None and not aap_role_mapping and not config.allow_all_authenticated:
            return False
        if result is None and (aap_role_mapping or config.allow_all_authenticated):
            logger.warning(
                "JMESPath extraction failed but login proceeding",
                reason="aap_role_mapping" if aap_role_mapping else "allow_all_authenticated",
                user_id=str(user.id),
                provider_id=str(provider_id),
            )
        if result is not None:
            desired_group_ids = desired_group_ids | result

    aap_validated = False
    if aap_role_mapping:
        aap_group_ids = await _resolve_aap_role_groups(db, raw_merged_claims, user.id, config)
        if aap_group_ids is None:
            return False
        desired_group_ids = desired_group_ids | aap_group_ids
        aap_validated = True

    has_matched = len(desired_group_ids) > 0 or aap_validated or config.allow_all_authenticated

    await _apply_group_membership_diff(db, user.id, provider_id, desired_group_ids, username=user.username)

    return has_matched


async def _apply_group_membership_diff(
    db: AsyncSession,
    user_id: UUID,
    provider_id: UUID,
    desired_group_ids: set[UUID],
    *,
    username: str,
) -> None:
    """Diff desired groups against all IdP-managed groups and apply changes.

    Session-scoped: clears IdP-managed memberships from *every* provider,
    then assigns only the groups resolved from the current login token.
    Groups that exist only in ``user_groups`` (no ``user_idp_groups`` row)
    are manually assigned and left untouched.

    Emits ``GroupMembershipEvent`` for each membership added or removed.
    """
    all_idp_rows = await db.exec(
        select(user_idp_groups.c.group_id, user_idp_groups.c.identity_provider_id).where(
            user_idp_groups.c.user_id == user_id,
        )
    )
    rows = list(all_idp_rows)
    all_idp_group_ids: set[UUID] = {row[0] for row in rows}
    previous_provider_ids: set[UUID] = {row[1] for row in rows}

    to_remove = all_idp_group_ids - desired_group_ids
    displaced_provider_ids = {row[1] for row in rows if row[0] in to_remove} - {provider_id}
    new_memberships: set[UUID] = set()

    if desired_group_ids:
        existing_rows = await db.exec(
            select(user_groups.c.group_id).where(
                user_groups.c.user_id == user_id,
                user_groups.c.group_id.in_(desired_group_ids),
            )
        )
        already_member: set[UUID] = set(existing_rows.all())
        new_memberships = desired_group_ids - already_member
        if new_memberships:
            await db.exec(
                user_groups.insert(),
                params=[{"user_id": user_id, "group_id": gid} for gid in new_memberships],
            )

    if to_remove:
        await db.exec(
            sa_delete(user_groups).where(
                user_groups.c.user_id == user_id,
                user_groups.c.group_id.in_(to_remove),
            )
        )

    await db.exec(
        sa_delete(user_idp_groups).where(
            user_idp_groups.c.user_id == user_id,
        )
    )
    if desired_group_ids:
        await db.exec(
            user_idp_groups.insert(),
            params=[
                {"user_id": user_id, "identity_provider_id": provider_id, "group_id": gid} for gid in desired_group_ids
            ],
        )

    added = len(desired_group_ids - all_idp_group_ids)
    removed = len(to_remove)
    if added or removed:
        logger.info(
            "Session-scoped IdP group sync",
            user_id=str(user_id),
            provider_id=str(provider_id),
            added=added,
            removed=removed,
            removed_group_ids=[str(gid) for gid in to_remove] if to_remove else [],
            previous_provider_ids=[str(pid) for pid in previous_provider_ids] if previous_provider_ids else [],
        )
    if displaced_provider_ids:
        logger.warning(
            "Cross-provider group displacement: groups from other providers removed",
            user_id=str(user_id),
            authenticating_provider_id=str(provider_id),
            displaced_provider_ids=[str(pid) for pid in displaced_provider_ids],
            groups_removed=removed,
        )

    await dispatch_membership_diff_events(
        db,
        user_id=user_id,
        username=username,
        added=new_memberships,
        removed=to_remove,
    )
