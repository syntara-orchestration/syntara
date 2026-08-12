"""Unit tests for auth error handlers and exceptions."""

from unittest.mock import MagicMock
from uuid import uuid4

from syntara.auth.error_handlers import (
    admin_delete_handler,
    admin_disable_no_other_admins_handler,
    admin_modify_handler,
    builtin_group_delete_handler,
    csrf_validation_error_handler,
    group_name_conflict_handler,
    group_not_found_handler,
    identity_on_builtin_user_handler,
    last_admin_removal_handler,
    last_sign_in_method_handler,
    password_on_federated_user_handler,
    service_account_ws_ticket_handler,
    session_store_unavailable_handler,
    user_already_in_group_handler,
    user_identity_not_found_handler,
    user_not_found_handler,
    user_not_in_group_handler,
    user_username_conflict_handler,
)
from syntara.auth.exceptions import (
    AdminDeleteError,
    AdminDisableNoOtherAdminsError,
    AdminModifyError,
    BuiltinGroupDeleteError,
    CSRFErrorCode,
    CSRFValidationError,
    GroupNameConflictError,
    GroupNotFoundError,
    IdentityOnBuiltinUserError,
    LastAdminRemovalError,
    LastSignInMethodError,
    PasswordOnFederatedUserError,
    ServiceAccountWSTicketError,
    SessionStoreUnavailableError,
    UserAlreadyInGroupError,
    UserIdentityNotFoundError,
    UserNotFoundError,
    UserNotInGroupError,
    UserUsernameConflictError,
)


def _make_request() -> MagicMock:
    request = MagicMock()
    request.url = "http://localhost:8000/api/v1/auth/users/123"
    request.method = "GET"
    return request


class TestExceptions:
    """Tests for auth exception classes."""

    def test_csrf_validation_error_default_message(self) -> None:
        exc = CSRFValidationError()
        assert exc.message == "CSRF validation failed"

    def test_csrf_validation_error_custom_message(self) -> None:
        exc = CSRFValidationError("CSRF cookie missing")
        assert exc.message == "CSRF cookie missing"

    def test_csrf_validation_error_default_error_code(self) -> None:
        exc = CSRFValidationError()
        assert exc.error_code == CSRFErrorCode.TOKEN_MISMATCH

    def test_csrf_validation_error_custom_error_code(self) -> None:
        exc = CSRFValidationError("msg", error_code=CSRFErrorCode.COOKIE_MISSING)
        assert exc.error_code == CSRFErrorCode.COOKIE_MISSING

    def test_user_identity_not_found_error(self) -> None:
        identity_id = uuid4()
        exc = UserIdentityNotFoundError(identity_id)
        assert str(identity_id) in str(exc)
        assert exc.identity_id == identity_id

    def test_user_not_found_error(self) -> None:
        user_id = uuid4()
        exc = UserNotFoundError(user_id)
        assert str(user_id) in str(exc)
        assert exc.user_id == user_id

    def test_user_username_conflict_error(self) -> None:
        exc = UserUsernameConflictError("admin")
        assert "admin" in str(exc)
        assert exc.username == "admin"

    def test_admin_modify_error(self) -> None:
        exc = AdminModifyError()
        assert "admin" in str(exc).lower()

    def test_last_sign_in_method_error(self) -> None:
        exc = LastSignInMethodError()
        assert "sign-in method" in str(exc).lower()

    def test_service_account_ws_ticket_error_default(self) -> None:
        exc = ServiceAccountWSTicketError()
        assert exc.message == "Service accounts cannot obtain WebSocket tickets"
        assert exc.service_account_id is None

    def test_service_account_ws_ticket_error_with_id(self) -> None:
        sa_id = str(uuid4())
        exc = ServiceAccountWSTicketError(service_account_id=sa_id)
        assert exc.service_account_id == sa_id
        assert exc.message == "Service accounts cannot obtain WebSocket tickets"

    def test_service_account_ws_ticket_error_custom_message(self) -> None:
        exc = ServiceAccountWSTicketError("Custom message")
        assert exc.message == "Custom message"


class TestErrorHandlers:
    """Tests for auth error handler functions."""

    def test_service_account_ws_ticket_handler_returns_403(self) -> None:
        sa_id = str(uuid4())
        exc = ServiceAccountWSTicketError(service_account_id=sa_id)
        response = service_account_ws_ticket_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"SERVICE_ACCOUNT_WS_TICKET_FORBIDDEN" in response.body
        assert response.headers["X-Auth-Failure-Type"] == "service_account_forbidden"

    def test_csrf_validation_error_handler_returns_403(self) -> None:
        exc = CSRFValidationError("CSRF token mismatch", error_code=CSRFErrorCode.TOKEN_MISMATCH)
        response = csrf_validation_error_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"CSRF_TOKEN_MISMATCH" in response.body
        assert b"CSRF validation failed" in response.body

    def test_user_identity_not_found_handler_returns_404(self) -> None:
        identity_id = uuid4()
        exc = UserIdentityNotFoundError(identity_id)
        response = user_identity_not_found_handler(_make_request(), exc)
        assert response.status_code == 404

    def test_user_not_found_handler_returns_404(self) -> None:
        exc = UserNotFoundError(uuid4())
        response = user_not_found_handler(_make_request(), exc)
        assert response.status_code == 404

    def test_user_username_conflict_handler_returns_409(self) -> None:
        exc = UserUsernameConflictError("taken")
        response = user_username_conflict_handler(_make_request(), exc)
        assert response.status_code == 409

    def test_admin_modify_handler_returns_403(self) -> None:
        exc = AdminModifyError()
        response = admin_modify_handler(_make_request(), exc)
        assert response.status_code == 403

    def test_group_not_found_handler_returns_404(self) -> None:
        exc = GroupNotFoundError(uuid4())
        response = group_not_found_handler(_make_request(), exc)
        assert response.status_code == 404

    def test_group_name_conflict_handler_returns_409(self) -> None:
        exc = GroupNameConflictError("taken")
        response = group_name_conflict_handler(_make_request(), exc)
        assert response.status_code == 409

    def test_user_already_in_group_handler_returns_409(self) -> None:
        exc = UserAlreadyInGroupError(uuid4(), uuid4())
        response = user_already_in_group_handler(_make_request(), exc)
        assert response.status_code == 409

    def test_user_not_in_group_handler_returns_404(self) -> None:
        exc = UserNotInGroupError(uuid4(), uuid4())
        response = user_not_in_group_handler(_make_request(), exc)
        assert response.status_code == 404

    def test_last_sign_in_method_handler_returns_409(self) -> None:
        exc = LastSignInMethodError()
        response = last_sign_in_method_handler(_make_request(), exc)
        assert response.status_code == 409

    def test_session_store_unavailable_handler_returns_503(self) -> None:
        exc = SessionStoreUnavailableError()
        request = MagicMock()
        request.url = "http://localhost:8000/api/v1/auth/callback?code=secret&state=abc"
        request.method = "GET"
        response = session_store_unavailable_handler(request, exc)
        assert response.status_code == 503
        body = bytes(response.body).decode()
        assert "SESSION_STORE_UNAVAILABLE" in body
        # Query string should be stripped from the instance URL
        assert "code=secret" not in body

    def test_admin_delete_handler_returns_403(self) -> None:
        exc = AdminDeleteError()
        response = admin_delete_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"ADMIN_DELETE_FORBIDDEN" in response.body

    def test_admin_disable_no_other_admins_handler_returns_403(self) -> None:
        exc = AdminDisableNoOtherAdminsError()
        response = admin_disable_no_other_admins_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"ADMIN_DISABLE_NO_OTHER_ADMINS" in response.body

    def test_last_admin_removal_handler_returns_403(self) -> None:
        exc = LastAdminRemovalError()
        response = last_admin_removal_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"LAST_ADMIN_REMOVAL_FORBIDDEN" in response.body

    def test_builtin_group_delete_handler_returns_403(self) -> None:
        exc = BuiltinGroupDeleteError("admins")
        response = builtin_group_delete_handler(_make_request(), exc)
        assert response.status_code == 403
        assert b"BUILTIN_GROUP_DELETE_FORBIDDEN" in response.body

    def test_password_on_federated_user_handler_returns_409(self) -> None:
        exc = PasswordOnFederatedUserError(uuid4())
        response = password_on_federated_user_handler(_make_request(), exc)
        assert response.status_code == 409
        assert b"PASSWORD_ON_FEDERATED_USER" in response.body

    def test_identity_on_builtin_user_handler_returns_409(self) -> None:
        exc = IdentityOnBuiltinUserError(uuid4())
        response = identity_on_builtin_user_handler(_make_request(), exc)
        assert response.status_code == 409
        assert b"IDENTITY_ON_BUILTIN_USER" in response.body


class TestNewExceptions:
    """Tests for new exception classes added in this branch."""

    def test_admin_delete_error(self) -> None:
        exc = AdminDeleteError()
        assert "admin" in str(exc).lower()
        assert "deleted" in str(exc).lower()

    def test_admin_disable_no_other_admins_error(self) -> None:
        exc = AdminDisableNoOtherAdminsError()
        assert "disable" in str(exc).lower()
        assert "admin" in str(exc).lower()

    def test_last_admin_removal_error(self) -> None:
        exc = LastAdminRemovalError()
        assert "admin" in str(exc).lower()

    def test_builtin_group_delete_error(self) -> None:
        exc = BuiltinGroupDeleteError("authenticated")
        assert "authenticated" in str(exc)
        assert "deleted" in str(exc).lower()

    def test_session_store_unavailable_error_default_message(self) -> None:
        exc = SessionStoreUnavailableError()
        assert exc.message == "Session service is temporarily unavailable"

    def test_session_store_unavailable_error_custom_message(self) -> None:
        exc = SessionStoreUnavailableError("Database connection failed")
        assert exc.message == "Database connection failed"

    def test_password_on_federated_user_error(self) -> None:
        user_id = uuid4()
        exc = PasswordOnFederatedUserError(user_id)
        assert str(user_id) in str(exc)
        assert exc.user_id == user_id

    def test_identity_on_builtin_user_error(self) -> None:
        user_id = uuid4()
        exc = IdentityOnBuiltinUserError(user_id)
        assert str(user_id) in str(exc)
        assert exc.user_id == user_id
