"""Authentication dependencies for FastAPI endpoints.

This module provides dependency injection functions for authenticating
requests and extracting user information from JWT tokens.

``get_current_user`` trusts the validated access token claims and constructs
a ``User`` object without a database round-trip.  Permission changes
therefore propagate within one access-token lifetime.

Usage:
    from syntara.auth.dependencies import get_current_user

    @app.get("/protected")
    async def protected_route(user: User = Depends(get_current_user)):
        return {"user": user.username}
"""

import threading
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.emitter import VERIFIED_ACTOR_STATE_KEY, AuditActorContext, actor_context_var
from syntara.auth.cookies import get_refresh_token_from_cookie
from syntara.auth.exceptions import (
    AuthenticationRequiredError,
    InvalidTokenError,
    TokenGloballyRevokedError,
)
from syntara.auth.services.token_service import TokenPayload, TokenService
from syntara.core.auth.jwt_utils import extract_actor_claims
from syntara.core.database.session import get_db
from syntara.core.lib.sanitization import strip_control_chars
from syntara.core.models import User
from syntara.core.models.principal import PrincipalType, make_service_user

# Optional bearer scheme - doesn't auto-raise 403
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    bearerFormat="JWT",
    description="JWT token authentication",
)


_token_service_instance: TokenService | None = None
_token_service_lock = threading.Lock()


def _get_token_service() -> TokenService:
    """Get cached token service instance.

    The ``TokenService`` (and its ``KeyManager``) are cached for the
    lifetime of the process.  Call ``clear_token_service_cache`` to
    force a reload (e.g. during emergency key rotation or in tests).

    Thread-safe: uses a lock to prevent concurrent initialization.
    """
    global _token_service_instance  # noqa: PLW0603
    with _token_service_lock:
        if _token_service_instance is None:
            _token_service_instance = TokenService()
        return _token_service_instance


def clear_token_service_cache() -> None:
    """Clear the cached TokenService, forcing a reload on next access.

    Also clears the underlying KeyManager cache so new keys are loaded.
    Use this for emergency key rotation or to prevent cross-test contamination.
    """
    global _token_service_instance  # noqa: PLW0603
    with _token_service_lock:
        _token_service_instance = None


def _safe_parse_uuid(value: str) -> UUID | None:
    """Parse a UUID string, returning ``None`` on failure."""
    try:
        return UUID(value)
    except ValueError:
        return None


async def _check_global_revocation(payload: TokenPayload, *, token_type: str, db: AsyncSession) -> None:
    """Reject the token if it was issued before the global revocation timestamp.

    Dispatches an audit event and raises ``TokenGloballyRevokedError``
    when the token is revoked.  Does nothing when no revocation
    timestamp is configured or the token was issued after it.

    Args:
        payload: Decoded token payload (must have ``iat`` and ``sub``).
        token_type: ``"access"`` or ``"refresh"`` — included in the
            audit event for observability.
        db: Active database session (reused from the request).

    Raises:
        InvalidTokenError: If the token has no ``iat`` claim.
        TokenGloballyRevokedError: If the token predates the revocation
            timestamp.

    """
    if payload.iat is None:
        raise InvalidTokenError

    from syntara.auth.services.global_revocation import is_token_globally_revoked  # noqa: PLC0415

    revocation_ts = await is_token_globally_revoked(payload.iat, db)
    if revocation_ts is not None:
        from syntara.audit.dispatcher import AuditEventDispatcher  # noqa: PLC0415
        from syntara.auth.audit.global_revocation import GlobalRevocationRejectEvent  # noqa: PLC0415

        AuditEventDispatcher.dispatch(
            GlobalRevocationRejectEvent(
                user_id=None if not payload.sub else _safe_parse_uuid(payload.sub),
                username=payload.preferred_username,
                token_issued_at=payload.iat.isoformat(),
                revocation_timestamp=revocation_ts.isoformat(),
                token_type=token_type,
                principal_type=PrincipalType.SERVICE_ACCOUNT if _is_service_account_token(payload) else None,
            )
        )
        raise TokenGloballyRevokedError


def _is_service_account_token(payload: TokenPayload) -> bool:
    return payload.token_type == "service_account"  # noqa: S105


def _set_verified_actor_context(request: Request, actor_ctx: AuditActorContext) -> None:
    """Propagate verified actor identity to the audit system.

    Sets both ``actor_context_var`` (for use within the current async
    task) and ``request.state`` (which survives the ``BaseHTTPMiddleware``
    task boundary so the outer ``AuditMiddleware`` can read it).
    """
    actor_context_var.set(actor_ctx)
    setattr(request.state, VERIFIED_ACTOR_STATE_KEY, actor_ctx)


def _set_verified_actor_context_from_user(request: Request, user: User) -> None:
    """Set audit actor context from a verified ``User``."""
    from syntara.audit.context_managers import build_actor_context  # noqa: PLC0415

    _set_verified_actor_context(request, build_actor_context(user))


def _set_verified_actor_context_from_payload(request: Request, payload: TokenPayload) -> None:
    """Set audit actor context from a verified ``TokenPayload``."""
    from syntara.audit.utils import sanitize_actor_username  # noqa: PLC0415

    actor_claims = extract_actor_claims(
        {
            "sub": payload.sub,
            "preferred_username": payload.preferred_username,
        }
    )

    actor_type = PrincipalType.SERVICE_ACCOUNT if _is_service_account_token(payload) else PrincipalType.USER

    _set_verified_actor_context(
        request,
        AuditActorContext(
            actor_id=actor_claims.actor_id,
            actor_username=sanitize_actor_username(actor_claims.actor_username),
            actor_type=actor_type,
        ),
    )


def _user_from_payload(payload: TokenPayload) -> User:
    """Construct a ``User`` instance from validated JWT claims.

    The returned object is **not** attached to any database session.

    Args:
        payload: Decoded and validated access-token payload.

    Returns:
        User populated from token claims.

    Raises:
        InvalidTokenError: If required claims are missing or malformed.

    """
    # Extract actor claims using shared utility to ensure consistency
    # with audit middleware claim extraction
    claims = {
        "sub": payload.sub,
        "preferred_username": payload.preferred_username,
    }
    actor_claims = extract_actor_claims(claims)

    if not actor_claims.actor_id:
        raise InvalidTokenError

    user_id = actor_claims.actor_id
    username = actor_claims.actor_username or payload.sub
    email = payload.email or f"{username}@unknown"
    # JWT claims from our own token service are already sanitized, but external
    # JWTs (e.g. delegated tokens) may not be — sanitize defensively.
    if payload.given_name:
        first_name = strip_control_chars(payload.given_name)
        last_name = strip_control_chars(payload.family_name) if payload.family_name else None
    elif payload.name:
        first_name = strip_control_chars(payload.name)
        last_name = None
    else:
        first_name = username
        last_name = None

    user = User(
        id=user_id,
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        is_enabled=True,
    )
    if _is_service_account_token(payload):
        object.__setattr__(user, "__principal_type__", PrincipalType.SERVICE_ACCOUNT)
    return user


def _user_from_cert(request: Request, cert_cn: str) -> User:
    """Build a User for a cert-authenticated internal service request.

    If the request carries an ``X-On-Behalf-Of`` header (trusted because
    the middleware only preserves it for cert-authenticated requests), the
    returned User has that UUID as its ``id`` — preserving ``created_by``
    attribution to the originating human user.

    Without the header, falls back to a deterministic service principal
    UUID derived from the cert CN so that FK constraints on ``created_by``
    remain valid.
    """
    on_behalf_of = request.headers.get("x-on-behalf-of")
    if on_behalf_of:
        user_id = _safe_parse_uuid(on_behalf_of)
        if user_id:
            return User(
                id=user_id,
                username=cert_cn,
                email=f"{cert_cn}@internal",
                first_name=cert_cn,
                is_enabled=True,
            )
    return make_service_user(cert_cn)


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> User:
    """Get the current authenticated user from JWT token claims or client cert.

    First checks for a valid JWT Bearer token. If absent, falls back to
    mTLS client certificate authentication (set by
    :class:`~syntara.auth.cert_middleware.ClientCertAuthMiddleware`).

    The ``User`` object is constructed entirely from the validated access-token
    claims -- no database round-trip is performed.  Permission or role changes
    therefore take up to one access-token lifetime to propagate to existing
    sessions.

    Tokens issued before the global revocation timestamp are hard-rejected
    with a 401 response.

    Args:
        request: FastAPI request object
        db: Database session (reused from the request for revocation check).
        credentials: HTTP Bearer credentials

    Returns:
        Authenticated User instance

    Raises:
        AuthenticationRequiredError: If no valid credentials provided
        InvalidTokenError: If token is invalid
        TokenGloballyRevokedError: If token was issued before the global
            revocation timestamp

    """
    if not credentials:
        if getattr(request.state, "is_cert_authenticated", False):
            user = _user_from_cert(request, request.state.cert_cn)
            _set_verified_actor_context_from_user(request, user)
            return user
        raise AuthenticationRequiredError

    # Validate token — set actor context immediately after verified decode
    # so audit attribution survives even if revocation checks reject the token.
    token_service = _get_token_service()
    payload: TokenPayload = token_service.decode_token(
        credentials.credentials,
        token_type="access",  # noqa: S106
    )
    _set_verified_actor_context_from_payload(request, payload)

    await _check_global_revocation(payload, token_type="access", db=db)  # noqa: S106

    user = _user_from_payload(payload)
    _set_verified_actor_context_from_user(request, user)
    return user


async def get_token_payload(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> TokenPayload:
    """Get the validated access token payload.

    Args:
        request: FastAPI request object
        db: Database session (reused from the request for revocation check).
        credentials: HTTP Bearer credentials

    Returns:
        Validated token payload with all claims

    Raises:
        AuthenticationRequiredError: If no valid credentials provided
        InvalidTokenError: If token is invalid
        TokenGloballyRevokedError: If token was issued before the global
            revocation timestamp

    """
    if not credentials:
        raise AuthenticationRequiredError

    token_service = _get_token_service()
    payload = token_service.decode_token(
        credentials.credentials,
        token_type="access",  # noqa: S106
    )
    _set_verified_actor_context_from_payload(request, payload)

    await _check_global_revocation(payload, token_type="access", db=db)  # noqa: S106

    return payload


async def get_refresh_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPayload:
    """Extract, decode, and validate the refresh token from the request cookie.

    Extracts the JWT from the ``ao_refresh_token`` HttpOnly cookie, decodes
    it as a refresh token, and checks whether it was issued before the global
    revocation timestamp.

    Performs CSRF validation first (compares the ``ao_csrf_token`` cookie
    seed against the ``X-CSRF-Token`` header via HMAC), then extracts the
    raw JWT from the ``ao_refresh_token`` HttpOnly cookie.

    Args:
        request: FastAPI request object
        db: Database session (reused from the request for revocation check).

    Returns:
        Decoded and validated refresh-token payload.

    Raises:
        CSRFValidationError: If CSRF validation fails (missing cookie,
            missing header, or token mismatch).
        AuthenticationRequiredError: If the refresh token cookie is missing
            or cannot be decoded.
        InvalidTokenError: If the token is structurally invalid.
        TokenGloballyRevokedError: If the token was issued before the global
            revocation timestamp.

    """
    from syntara.auth.csrf import validate_csrf  # noqa: PLC0415

    validate_csrf(request)

    raw_token = get_refresh_token_from_cookie(request)
    if not raw_token:
        raise AuthenticationRequiredError

    token_service = _get_token_service()
    try:
        payload = token_service.decode_token(
            raw_token,
            token_type="refresh",  # noqa: S106
        )
    except InvalidTokenError:
        raise
    except Exception as e:
        raise AuthenticationRequiredError from e

    _set_verified_actor_context_from_payload(request, payload)

    await _check_global_revocation(payload, token_type="refresh", db=db)  # noqa: S106

    return payload
