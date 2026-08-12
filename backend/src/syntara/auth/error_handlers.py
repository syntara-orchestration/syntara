"""RFC 9457 compliant error handlers for authentication exceptions.

This module provides error handlers for authentication and authorization
exceptions, returning responses in RFC 9457 Problem Details format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import Request, status

from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

if TYPE_CHECKING:
    from fastapi.responses import JSONResponse

    from syntara.auth.exceptions import (
        AdminDeleteError,
        AdminDisableNoOtherAdminsError,
        AdminModifyError,
        AuthenticationRequiredError,
        BuiltinGroupDeleteError,
        CSRFValidationError,
        GroupNameConflictError,
        GroupNamesNotFoundError,
        GroupNotFoundError,
        IdentityOnBuiltinUserError,
        InvalidTokenError,
        LastAdminRemovalError,
        LastSignInMethodError,
        PasswordOnFederatedUserError,
        RefreshTokenRevokedError,
        ServiceAccountWSTicketError,
        SessionStoreUnavailableError,
        TokenExpiredError,
        TokenGloballyRevokedError,
        UserAlreadyInGroupError,
        UserEmailConflictError,
        UserIdentityNotFoundError,
        UserNotFoundError,
        UserNotInGroupError,
        UserUsernameConflictError,
    )

logger = structlog.stdlib.get_logger(__name__)


def session_store_unavailable_handler(
    request: Request,
    exc: SessionStoreUnavailableError,
) -> JSONResponse:
    """Handle SessionStoreUnavailableError with RFC 9457 format."""
    # Strip query string to avoid leaking sensitive params (e.g. OIDC code/state)
    safe_url = str(request.url).split("?", 1)[0]

    logger.error(
        "Session store unavailable",
        path=safe_url,
        method=request.method,
    )

    return create_problem_details_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        problem_type=PROBLEM_TYPES["service_unavailable"],
        title="Service Unavailable",
        detail=exc.message,
        code="SESSION_STORE_UNAVAILABLE",
        retryable=True,
        instance=safe_url,
    )


def csrf_validation_error_handler(
    request: Request,
    exc: CSRFValidationError,
) -> JSONResponse:
    """Handle CSRFValidationError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The CSRF validation exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning(
        "CSRF validation failed",
        reason=exc.message,
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail="CSRF validation failed",
        code=exc.error_code,
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "csrf_failed"
    return response


def service_account_ws_ticket_handler(
    request: Request,
    exc: ServiceAccountWSTicketError,
) -> JSONResponse:
    """Handle ServiceAccountWSTicketError with RFC 9457 format."""
    logger.warning(
        "Service account attempted WebSocket ticket",
        service_account_id=exc.service_account_id,
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail=exc.message,
        code="SERVICE_ACCOUNT_WS_TICKET_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "service_account_forbidden"
    return response


def authentication_required_handler(
    request: Request,
    exc: AuthenticationRequiredError,
) -> JSONResponse:
    """Handle AuthenticationRequiredError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The authentication required exception

    Returns:
        RFC 9457 compliant 401 error response

    """
    logger.warning(
        "Authentication required",
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Unauthorized",
        detail=exc.message,
        code="AUTHENTICATION_REQUIRED",
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "missing_credentials"
    return response


def token_expired_handler(
    request: Request,
    exc: TokenExpiredError,
) -> JSONResponse:
    """Handle TokenExpiredError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The token expired exception

    Returns:
        RFC 9457 compliant 401 error response

    """
    logger.warning(
        "Token expired",
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["token_expired"],
        title="Token Expired",
        detail=exc.message,
        code="TOKEN_EXPIRED",
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "expired_token"
    return response


def invalid_token_handler(
    request: Request,
    exc: InvalidTokenError,
) -> JSONResponse:
    """Handle InvalidTokenError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The invalid token exception

    Returns:
        RFC 9457 compliant 401 error response

    """
    logger.warning(
        "Invalid token",
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Unauthorized",
        detail=exc.message,
        code="INVALID_TOKEN",
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "invalid_token"
    return response


def refresh_token_revoked_handler(
    request: Request,
    exc: RefreshTokenRevokedError,
) -> JSONResponse:
    """Handle RefreshTokenRevokedError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The refresh token revoked exception

    Returns:
        RFC 9457 compliant 401 error response

    """
    logger.warning(
        "Refresh token revoked",
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Unauthorized",
        detail=exc.message,
        code="REFRESH_TOKEN_REVOKED",
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = "refresh_revoked"
    return response


def token_globally_revoked_handler(
    request: Request,
    exc: TokenGloballyRevokedError,
) -> JSONResponse:
    """Handle TokenGloballyRevokedError with RFC 9457 format.

    Clears the ``ao_refresh_token`` cookie so the client does not
    keep retrying with a revoked refresh token.

    Args:
        request: FastAPI request object
        exc: The token globally revoked exception

    Returns:
        RFC 9457 compliant 401 error response with cleared cookie

    """
    from syntara.auth.cookies import clear_refresh_cookie  # noqa: PLC0415

    logger.warning(
        "Token globally revoked",
        path=str(request.url),
        method=request.method,
    )

    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Unauthorized",
        detail=exc.message,
        code="TOKEN_GLOBALLY_REVOKED",
        retryable=False,
        instance=str(request.url),
    )
    clear_refresh_cookie(response)
    response.headers["X-Auth-Failure-Type"] = "globally_revoked"
    return response


def group_not_found_handler(
    request: Request,
    exc: GroupNotFoundError,
) -> JSONResponse:
    """Handle GroupNotFoundError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The group not found exception

    Returns:
        RFC 9457 compliant 404 error response

    """
    logger.warning("Group not found", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Group Not Found",
        detail="The requested group was not found",
        code="GROUP_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def group_name_conflict_handler(
    request: Request,
    exc: GroupNameConflictError,
) -> JSONResponse:
    """Handle GroupNameConflictError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The group name conflict exception

    Returns:
        RFC 9457 compliant 409 error response

    """
    logger.warning("Group name conflict", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Group Name Conflict",
        detail="A group with this name already exists",
        code="GROUP_NAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def group_names_not_found_handler(
    request: Request,
    exc: GroupNamesNotFoundError,
) -> JSONResponse:
    """Handle GroupNamesNotFoundError with RFC 9457 format."""
    logger.warning("Groups not found", names=exc.names)

    return create_problem_details_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        problem_type=PROBLEM_TYPES["validation_error"],
        title="Groups Not Found",
        detail=f"The following groups do not exist: {', '.join(exc.names)}",
        code="GROUPS_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


# ============================================================================
# User error handlers
# ============================================================================


def user_identity_not_found_handler(
    request: Request,
    exc: UserIdentityNotFoundError,
) -> JSONResponse:
    """Handle UserIdentityNotFoundError with RFC 9457 format."""
    logger.warning("User identity not found", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="User Identity Not Found",
        detail="The requested user identity was not found",
        code="USER_IDENTITY_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def last_sign_in_method_handler(
    request: Request,
    exc: LastSignInMethodError,
) -> JSONResponse:
    """Handle LastSignInMethodError with RFC 9457 format."""
    logger.warning("Attempted to remove last sign-in method", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Last Sign-In Method",
        detail=str(exc),
        code="LAST_SIGN_IN_METHOD",
        retryable=False,
        instance=str(request.url),
    )


def user_not_found_handler(
    request: Request,
    exc: UserNotFoundError,
) -> JSONResponse:
    """Handle UserNotFoundError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The user not found exception

    Returns:
        RFC 9457 compliant 404 error response

    """
    logger.warning("User not found", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="User Not Found",
        detail="The requested user was not found",
        code="USER_NOT_FOUND",
        retryable=False,
        instance=str(request.url),
    )


def user_username_conflict_handler(
    request: Request,
    exc: UserUsernameConflictError,
) -> JSONResponse:
    """Handle UserUsernameConflictError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The username conflict exception

    Returns:
        RFC 9457 compliant 409 error response

    """
    logger.warning("Username conflict", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Username Conflict",
        detail="A user with this username already exists",
        code="USER_USERNAME_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def user_email_conflict_handler(
    request: Request,
    exc: UserEmailConflictError,
) -> JSONResponse:
    """Handle UserEmailConflictError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The email conflict exception

    Returns:
        RFC 9457 compliant 409 error response

    """
    logger.warning("Email conflict", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["name_conflict"],
        title="Email Conflict",
        detail="A user with this email already exists",
        code="USER_EMAIL_CONFLICT",
        retryable=False,
        instance=str(request.url),
    )


def admin_modify_handler(
    request: Request,
    exc: AdminModifyError,
) -> JSONResponse:
    """Handle AdminModifyError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The admin modify exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning("Attempted to modify built-in admin properties", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail="The built-in admin account properties cannot be modified",
        code="ADMIN_MODIFY_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


def admin_delete_handler(
    request: Request,
    exc: AdminDeleteError,
) -> JSONResponse:
    """Handle AdminDeleteError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The admin delete exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning("Attempted to delete built-in admin", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail="The built-in admin account cannot be deleted",
        code="ADMIN_DELETE_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


def admin_disable_no_other_admins_handler(
    request: Request,
    exc: AdminDisableNoOtherAdminsError,
) -> JSONResponse:
    """Handle AdminDisableNoOtherAdminsError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning("Attempted to disable last enabled admin", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail="Cannot disable the last enabled user in the admins group",
        code="ADMIN_DISABLE_NO_OTHER_ADMINS",
        retryable=False,
        instance=str(request.url),
    )


def last_admin_removal_handler(
    request: Request,
    exc: LastAdminRemovalError,
) -> JSONResponse:
    """Handle LastAdminRemovalError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning("Attempted to remove last admin from admins group", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail="Cannot remove the last enabled admin user from the admins group",
        code="LAST_ADMIN_REMOVAL_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


def builtin_group_delete_handler(
    request: Request,
    exc: BuiltinGroupDeleteError,
) -> JSONResponse:
    """Handle BuiltinGroupDeleteError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The exception

    Returns:
        RFC 9457 compliant 403 error response

    """
    logger.warning("Attempted to delete builtin group", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_403_FORBIDDEN,
        problem_type=PROBLEM_TYPES["forbidden"],
        title="Forbidden",
        detail=str(exc),
        code="BUILTIN_GROUP_DELETE_FORBIDDEN",
        retryable=False,
        instance=str(request.url),
    )


# ============================================================================
# Auth type exclusivity error handlers
# ============================================================================


def password_on_federated_user_handler(
    request: Request,
    exc: PasswordOnFederatedUserError,
) -> JSONResponse:
    """Handle PasswordOnFederatedUserError with RFC 9457 format."""
    logger.warning("Attempted to set password on federated user", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Password Not Allowed",
        detail="Cannot set a password on a federated user",
        code="PASSWORD_ON_FEDERATED_USER",
        retryable=False,
        instance=str(request.url),
    )


def identity_on_builtin_user_handler(
    request: Request,
    exc: IdentityOnBuiltinUserError,
) -> JSONResponse:
    """Handle IdentityOnBuiltinUserError with RFC 9457 format."""
    logger.warning("Attempted to link identity to built-in user", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Identity Link Not Allowed",
        detail="Cannot link a federated identity to a built-in user",
        code="IDENTITY_ON_BUILTIN_USER",
        retryable=False,
        instance=str(request.url),
    )


# ============================================================================
# Membership error handlers
# ============================================================================


def user_already_in_group_handler(
    request: Request,
    exc: UserAlreadyInGroupError,
) -> JSONResponse:
    """Handle UserAlreadyInGroupError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The user already in group exception

    Returns:
        RFC 9457 compliant 409 error response

    """
    logger.warning("User already in group", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_409_CONFLICT,
        problem_type=PROBLEM_TYPES["resource_conflict"],
        title="Membership Conflict",
        detail="The user is already a member of this group",
        code="USER_ALREADY_IN_GROUP",
        retryable=False,
        instance=str(request.url),
    )


def user_not_in_group_handler(
    request: Request,
    exc: UserNotInGroupError,
) -> JSONResponse:
    """Handle UserNotInGroupError with RFC 9457 format.

    Args:
        request: FastAPI request object
        exc: The user not in group exception

    Returns:
        RFC 9457 compliant 404 error response

    """
    logger.warning("User not in group", exc_info=exc)

    return create_problem_details_response(
        status_code=status.HTTP_404_NOT_FOUND,
        problem_type=PROBLEM_TYPES["resource_not_found"],
        title="Membership Not Found",
        detail="The user is not a member of this group",
        code="USER_NOT_IN_GROUP",
        retryable=False,
        instance=str(request.url),
    )
