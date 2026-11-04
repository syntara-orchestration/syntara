"""Shared permission checkers for service account resources."""

from syntara.authz.dependencies import PermissionChecker
from syntara.service_accounts.models.service_account import ServiceAccount


def service_account_checker(action: str) -> PermissionChecker:
    """Build a checker for an action on a specific service account.

    Service accounts are project-less, so ownership (``created_by``) is the
    only per-resource scope the checker can resolve.
    """
    return PermissionChecker(
        "service_account",
        action,
        resource_model=ServiceAccount,
        resource_id_param="service_account_id",
        owner_field="created_by",
    )
