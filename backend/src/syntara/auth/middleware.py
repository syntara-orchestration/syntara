"""Stale token rejection and disabled-principal enforcement middleware.

Checks whether the authenticated principal's access token has an outdated
``token_ver`` claim by comparing it against the ``token_version`` column
on the users or service_accounts table.  When stale, returns a 401
``TOKEN_STALE`` response so the client re-authenticates.

Also rejects requests from disabled users and disabled/deleted service
accounts with a 401 response.

Uses in-process TTLCaches (5s) to avoid a DB query on every request.
"""

from datetime import UTC, datetime

import structlog
from cachetools import TTLCache
from fastapi import status
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from syntara.auth.dependencies import _set_verified_actor_context_from_payload
from syntara.auth.services.token_service import TokenPayload, TokenService
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.error_handlers import PROBLEM_TYPES, create_problem_details_response

logger = structlog.stdlib.get_logger(__name__)

_user_status_cache: TTLCache[str, tuple[int, bool]] = TTLCache(maxsize=4096, ttl=5)
_SA_NOT_FOUND: tuple[str, int] = ("__not_found__", -1)
_sa_status_cache: TTLCache[str, tuple[str, int]] = TTLCache(maxsize=4096, ttl=5)
_stale_audit_cache: TTLCache[str, bool] = TTLCache(maxsize=4096, ttl=60)

_GET_USER_STATUS_SQL = "SELECT token_version, is_enabled FROM users WHERE id = :uid"
_GET_SA_STATUS_SQL = "SELECT sa.status, sa.token_version FROM service_accounts sa WHERE sa.id = :sa_id"
_SA_CRED_NOT_FOUND: tuple[str, None] = ("__cred_not_found__", None)
_cred_status_cache: TTLCache[str, tuple[str, datetime | None]] = TTLCache(maxsize=4096, ttl=5)
_GET_CRED_STATUS_SQL = "SELECT sac.status, sac.expires_at FROM service_account_credentials sac WHERE sac.id = :cred_id"


async def _check_sa_status(sa_id: str) -> tuple[str, int] | None:
    """Look up service account status (cached 5s). Returns (status, token_version) or None if not found."""
    cached = _sa_status_cache.get(sa_id)
    if cached is not None:
        return None if cached is _SA_NOT_FOUND else cached

    async with AsyncSessionLocal() as session:
        result = await session.exec(  # type: ignore[call-overload]
            text(_GET_SA_STATUS_SQL),
            params={"sa_id": sa_id},
        )
        row = result.one_or_none()
        if row:
            status_val, token_ver = str(row[0]), int(row[1])
            _sa_status_cache[sa_id] = (status_val, token_ver)
            return status_val, token_ver
        _sa_status_cache[sa_id] = _SA_NOT_FOUND
        return None


async def _check_cred_status(cred_id: str) -> tuple[str, datetime | None] | None:
    """Look up credential status and expiry (cached 5s). Returns (status, expires_at) or None if not found."""
    cached = _cred_status_cache.get(cred_id)
    if cached is not None:
        return None if cached is _SA_CRED_NOT_FOUND else cached

    async with AsyncSessionLocal() as session:
        result = await session.exec(  # type: ignore[call-overload]
            text(_GET_CRED_STATUS_SQL),
            params={"cred_id": cred_id},
        )
        row = result.one_or_none()
        if row:
            val = (str(row[0]), row[1])
            _cred_status_cache[cred_id] = val
            return val
        _cred_status_cache[cred_id] = _SA_CRED_NOT_FOUND
        return None


def _make_sa_rejection(
    request: Request,
    *,
    detail: str,
    code: str,
    failure_type: str,
) -> Response:
    """Build a 401 response for an SA-related rejection."""
    response = create_problem_details_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        problem_type=PROBLEM_TYPES["unauthorized"],
        title="Unauthorized",
        detail=detail,
        code=code,
        retryable=False,
        instance=str(request.url),
    )
    response.headers["X-Auth-Failure-Type"] = failure_type
    return response


async def _check_sa_identity(request: Request, sa_id: str, payload: TokenPayload) -> Response | None:
    """Check SA existence, status, and token version. Returns a rejection Response or None."""
    try:
        sa_result = await _check_sa_status(sa_id)
    except Exception:  # noqa: BLE001
        logger.debug("SA status check failed, skipping", exc_info=True)
        return None

    if sa_result is None:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.sa_rejection import DisabledSARejectionEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            DisabledSARejectionEvent(service_account_id=sa_id, sa_status="deleted", is_alive=False)
        )
        logger.warning("Rejected request from deleted service account", service_account_id=sa_id)
        return _make_sa_rejection(
            request, detail="Service account no longer exists", code="SA_DELETED", failure_type="deleted_sa"
        )

    status_val, current_ver = sa_result
    token_ver = payload.token_version or 0

    if status_val != "active":
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.sa_rejection import DisabledSARejectionEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            DisabledSARejectionEvent(service_account_id=sa_id, sa_status=status_val, is_alive=True)
        )
        logger.warning("Rejected request from disabled service account", service_account_id=sa_id, sa_status=status_val)
        return _make_sa_rejection(
            request, detail="Service account is disabled", code="SA_DISABLED", failure_type="disabled_sa"
        )

    if current_ver > token_ver:
        if sa_id not in _stale_audit_cache:
            from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
            from syntara.auth.audit.sa_rejection import StaleSATokenDetectionEvent  # noqa: PLC0415

            AuditEventDispatcher.dispatch(
                StaleSATokenDetectionEvent(
                    service_account_id=sa_id, token_version=token_ver, current_version=current_ver
                )
            )
            _stale_audit_cache[sa_id] = True

        logger.warning(
            "Rejected request with stale service account token",
            service_account_id=sa_id,
            token_version=token_ver,
            current_version=current_ver,
        )
        return _make_sa_rejection(
            request,
            detail="Service account token has been revoked",
            code="SA_TOKEN_REVOKED",
            failure_type="revoked_sa_token",
        )

    return None


async def _check_sa_credential(request: Request, sa_id: str, cred_id: str | None) -> Response | None:
    """Check SA credential existence and status. Returns a rejection Response or None."""
    if cred_id is None:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.sa_rejection import MissingSACredentialClaimEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(MissingSACredentialClaimEvent(service_account_id=sa_id))
        logger.warning("Rejected SA token missing cred_id claim", service_account_id=sa_id)
        return _make_sa_rejection(
            request,
            detail="Service account token has been revoked",
            code="SA_TOKEN_REVOKED",
            failure_type="revoked_sa_token",
        )

    try:
        cred_result = await _check_cred_status(cred_id)
    except Exception:  # noqa: BLE001
        logger.debug("Credential status check failed, skipping", exc_info=True)
        return None

    if cred_result is None or cred_result[0] != "active":
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.sa_rejection import DisabledSACredentialRejectionEvent  # noqa: PLC0415

        resolved_status = cred_result[0] if cred_result else "deleted"
        AuditEventDispatcher.dispatch(
            DisabledSACredentialRejectionEvent(
                service_account_id=sa_id, credential_id=cred_id, credential_status=resolved_status
            )
        )
        logger.warning(
            "Rejected request: SA credential disabled/deleted",
            service_account_id=sa_id,
            credential_id=cred_id,
            credential_status=resolved_status,
        )
        return _make_sa_rejection(
            request,
            detail="Service account credential is disabled",
            code="SA_CREDENTIAL_DISABLED",
            failure_type="disabled_sa_credential",
        )

    _, expires_at = cred_result
    if expires_at is not None and datetime.now(UTC) >= expires_at:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.sa_rejection import ExpiredSACredentialRejectionEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            ExpiredSACredentialRejectionEvent(service_account_id=sa_id, credential_id=cred_id, expires_at=expires_at)
        )
        logger.warning(
            "Rejected request: SA credential expired",
            service_account_id=sa_id,
            credential_id=cred_id,
            expires_at=expires_at.isoformat(),
        )
        return _make_sa_rejection(
            request,
            detail="Service account credential has expired",
            code="SA_CREDENTIAL_EXPIRED",
            failure_type="expired_sa_credential",
        )

    return None


class StaleTokenMiddleware(BaseHTTPMiddleware):
    """Enforce disabled/deleted principal rejection and stale-token detection."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Reject disabled/deleted principals, and stale tokens."""
        auth_header = request.headers.get("authorization", "")
        if auth_header[:7].lower() != "bearer ":
            return await call_next(request)

        token = auth_header[7:]

        try:
            token_service = TokenService()
            payload = token_service.decode_token(token, token_type="access")  # noqa: S106
        except Exception:  # noqa: BLE001
            logger.debug("Token decode failed, skipping middleware checks", exc_info=True)
            return await call_next(request)

        _set_verified_actor_context_from_payload(request, payload)

        is_sa_token = payload.token_type == "service_account"  # noqa: S105

        if is_sa_token:
            return await self._handle_sa_token(request, call_next, payload)
        return await self._handle_user_token(request, call_next, payload)

    async def _handle_sa_token(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        payload: TokenPayload,
    ) -> Response:
        """Reject requests from disabled/deleted or token-revoked service accounts."""
        sa_id = payload.sub

        rejection = await _check_sa_identity(request, sa_id, payload)
        if rejection is not None:
            return rejection

        rejection = await _check_sa_credential(request, sa_id, payload.credential_id)
        if rejection is not None:
            return rejection

        return await call_next(request)

    async def _handle_user_token(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
        payload: TokenPayload,
    ) -> Response:
        """Reject disabled users and stale user tokens."""
        user_id = payload.sub
        token_ver = payload.token_version or 0
        current_ver: int = 0
        is_enabled: bool = True
        status_resolved: bool = False

        try:
            cached = _user_status_cache.get(user_id)
            if cached is not None:
                current_ver, is_enabled = cached
            else:
                async with AsyncSessionLocal() as session:
                    result = await session.exec(  # type: ignore[call-overload]
                        text(_GET_USER_STATUS_SQL),
                        params={"uid": user_id},
                    )
                    row = result.one_or_none()
                    if row:
                        current_ver, is_enabled = row[0], row[1]
                    else:
                        current_ver, is_enabled = 0, True
                    _user_status_cache[user_id] = (current_ver, is_enabled)

            status_resolved = True

        except Exception:  # noqa: BLE001
            logger.debug("User status check failed, skipping", exc_info=True)

        # CVE-2026-48710: use scope["path"] (raw ASGI path) instead of
        # request.url.path which is reconstructed from the Host header.
        normalized_path = request.scope["path"].rstrip("/")
        is_logout = normalized_path == "/api/v1/auth/logout"
        is_auth_lifecycle = is_logout or normalized_path == "/api/v1/auth/refresh"
        if status_resolved and not is_enabled and not is_logout:
            from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
            from syntara.auth.audit.disabled_user_rejection import (  # noqa: PLC0415
                DisabledUserRejectionEvent,
                RejectionContext,
            )

            AuditEventDispatcher.dispatch(
                DisabledUserRejectionEvent(
                    user_id=user_id, context=RejectionContext.MIDDLEWARE, user_name=payload.preferred_username
                )
            )
            logger.warning("Rejected request from disabled user", user_id=user_id)
            response = create_problem_details_response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                problem_type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="User account is disabled",
                code="ACCOUNT_DISABLED",
                retryable=False,
                instance=str(request.url),
            )
            response.headers["X-Auth-Failure-Type"] = "disabled_user"
            return response

        if status_resolved and current_ver > token_ver and not is_auth_lifecycle:
            if user_id not in _stale_audit_cache:
                from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
                from syntara.auth.audit.stale_token_detection import StaleTokenDetectionEvent  # noqa: PLC0415

                AuditEventDispatcher.dispatch(
                    StaleTokenDetectionEvent(
                        user_id=user_id,
                        token_version=token_ver,
                        current_version=current_ver,
                        user_name=payload.preferred_username,
                    )
                )
                _stale_audit_cache[user_id] = True

            logger.warning("Rejected request with stale token", user_id=user_id)
            response = create_problem_details_response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                problem_type=PROBLEM_TYPES["unauthorized"],
                title="Unauthorized",
                detail="Token is outdated, please refresh",
                code="TOKEN_STALE",
                retryable=True,
                instance=str(request.url),
            )
            response.headers["X-Auth-Failure-Type"] = "stale_token"
            return response

        return await call_next(request)
