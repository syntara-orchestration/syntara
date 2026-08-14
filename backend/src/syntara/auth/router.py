"""Authentication API endpoints.

This module provides endpoints for JWT token management, including:
- Login (username/password authentication)
- Token refresh (refresh token read from HttpOnly cookie)
- Logout (session revocation, clears refresh cookie)
- Current user information
- Auth providers listing (public, for login page)
- OIDC authorization code flow (authorize + callback)
"""

import base64
import json
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, NoReturn
from urllib.parse import quote, urlencode, urlparse
from uuid import UUID

import structlog
from fastapi import Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import insert as sa_insert
from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.context_managers import actor_context
from syntara.audit.decorators import audit
from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import AuditActorContext
from syntara.audit.models.audit_event import EventCategory
from syntara.audit.sanitization import EMAIL_PATTERN
from syntara.auth.audit.login_attempt import LoginAttemptEvent, LoginErrorReason, LoginMethod
from syntara.auth.audit.oidc_flow import OIDCFlowEvent, OIDCStage
from syntara.auth.audit.session_lifecycle import SessionAction, SessionLifecycleEvent
from syntara.auth.audit.user_login import AMR, UserLoginEvent
from syntara.auth.cookies import (
    clear_csrf_cookie,
    clear_refresh_cookie,
    get_refresh_token_from_cookie,
    set_csrf_cookie,
    set_refresh_cookie,
)
from syntara.auth.csrf import (
    CSRF_COOKIE_NAME,
    ERR_COOKIE_MISSING,
    derive_csrf_form_token,
    generate_csrf_seed,
)
from syntara.auth.dependencies import (
    _get_token_service,
    get_refresh_token,
    get_token_payload,
)
from syntara.auth.exceptions import (
    AuthenticationRequiredError,
    CSRFErrorCode,
    CSRFValidationError,
    InvalidTokenError,
    OIDCCallbackError,
    OIDCErrorCode,
    RefreshTokenRevokedError,
    ServiceAccountWSTicketError,
    SessionStoreUnavailableError,
)
from syntara.auth.passwords import verify_password
from syntara.auth.schemas import (
    AccessTokenResponse,
    AuthProviderInfo,
    AuthProvidersResponse,
    CsrfTokenResponse,
    LoginRequest,
    UserInfo,
    WebSocketTicketResponse,
)
from syntara.auth.services.idp_group_sync import sync_idp_groups
from syntara.auth.services.oidc_service import OIDCError, OIDCService, _is_ssl_verification_error
from syntara.auth.services.token_service import TokenPayload
from syntara.auth.session import SessionInfo, create_session_store
from syntara.authz.audit.group_membership import GroupMembershipEvent
from syntara.authz.dependencies import get_authz_evaluator
from syntara.authz.engine import AuthzRequest, authorize
from syntara.authz.resolver import AUTHENTICATED_GROUP_NAME
from syntara.core.config.base import get_encryption_key, get_settings
from syntara.core.constants import FieldLimits
from syntara.core.database.session import get_db
from syntara.core.lib.encryption import SecretEncryptor, key_from_string
from syntara.core.lib.sanitization import strip_control_chars
from syntara.core.models import Group, User, UserIdentity
from syntara.core.models.group import user_groups
from syntara.core.models.principal import PrincipalType
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import SUBJECT_MAX_LENGTH
from syntara.core.nexus_router import NO_PERMISSION, NexusRouter
from syntara.core.services.secret_service import create_secret_service
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.identity_provider_configuration import (
    IdentityProviderConfigurationTypes,
    OIDCConfiguration,
)
from syntara.service_accounts.models.service_account import ServiceAccount, ServiceAccountStatus
from syntara.service_accounts.models.service_account_credential import (
    ServiceAccountCredential,
    ServiceAccountCredentialStatus,
)
from syntara.settings.cache.settings_cache import get_runtime_settings
from syntara.users.services.user_identity_service import UserIdentityService

logger = structlog.stdlib.get_logger(__name__)


async def _get_user_group_names(db: AsyncSession, user_id: UUID) -> list[str]:
    """Fetch group names for a user to include in JWT claims."""
    result = await db.exec(
        select(Group.name)
        .join(user_groups, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
        .where(
            user_groups.c.user_id == user_id,
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
        .order_by(col(Group.name))
    )
    return list(result.all())


router = NexusRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    operation_id="login",
    dependencies=[NO_PERMISSION],
    summary="Login with username and password",
    description="""
    Authenticate with a username and password to receive a JWT access token.

    On success the response body contains an access token and the
    ``ao_refresh_token`` HttpOnly cookie is set.
    """,
    response_description="Successful authentication",
    responses={
        401: {"description": "Invalid username or password"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    """Login with username and password.

    Args:
        body: Login credentials (username and password)
        request: FastAPI request object (for client metadata)
        response: FastAPI response object (refresh cookie set here)
        db: Database session

    Returns:
        Access token response (refresh token travels via Set-Cookie header)

    Raises:
        AuthenticationRequiredError: If credentials are invalid

    """
    settings = get_settings()

    username = body.username.lower()
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # Look up user by username (case-insensitive)
    result = await db.exec(
        select(User).filter(
            User.username == username,  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    user = result.one_or_none()

    if not user or not user.password_hash:
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(username=username, method=LoginMethod.PASSWORD, error_type=LoginErrorReason.UNKNOWN_USER)
        )
        raise AuthenticationRequiredError

    if not user.is_builtin:
        cache = get_runtime_settings()
        local_login_enabled = await cache.get_bool("authentication.local_login_enabled")
        if not local_login_enabled:
            AuditEventDispatcher.dispatch(
                LoginAttemptEvent(
                    username=username,
                    method=LoginMethod.PASSWORD,
                    error_type=LoginErrorReason.LOCAL_LOGIN_DISABLED,
                    user_id=user.id,
                )
            )
            raise AuthenticationRequiredError

    if not verify_password(body.password, user.password_hash):
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=username,
                method=LoginMethod.PASSWORD,
                error_type=LoginErrorReason.BAD_PASSWORD,
                user_id=user.id,
            )
        )
        raise AuthenticationRequiredError

    if not user.is_enabled:
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(
                username=username,
                method=LoginMethod.PASSWORD,
                error_type=LoginErrorReason.INACTIVE_ACCOUNT,
                user_id=user.id,
            )
        )
        raise AuthenticationRequiredError

    # Resolve group names for JWT claims (before modifying session state)
    user_group_names = await _get_user_group_names(db, user.id)

    # token_version is now a column on the User model — read directly
    token_version = user.token_version
    is_first_login = user.last_login is None

    # Create access token
    token_service = _get_token_service()
    access_token = token_service.create_access_token(
        subject_id=user.id,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        amr=[AMR.PASSWORD],
        idp="local",
        groups=user_group_names,
        token_version=token_version,
    )

    # Create refresh token and store session in PostgreSQL
    refresh_token_str, jti, _exp = token_service.create_refresh_token(user.id)

    try:
        store = create_session_store(db)
        await store.create(
            jti=jti,
            user_id=user.id,
            device=user_agent,
            ip_address=client_host,
            amr=[AMR.PASSWORD],
            idp="local",
        )
    except SQLAlchemyError as exc:
        AuditEventDispatcher.dispatch(
            SessionLifecycleEvent(
                action=SessionAction.CREATE,
                user_id=user.id,
                username=user.username,
                jti=jti,
                idp="local",
                error_type=type(exc).__name__,
            )
        )
        logger.exception("Session store failed during login", error=str(exc))
        raise SessionStoreUnavailableError from exc
    AuditEventDispatcher.dispatch(
        SessionLifecycleEvent(
            action=SessionAction.CREATE, user_id=user.id, username=user.username, jti=jti, idp="local"
        )
    )

    # Login has no JWT yet, so audit middleware cannot attribute the CRUD
    # last_login write — establish the logging-in user as actor (AAP-83651).
    with actor_context(actor=user):
        user.update_last_login()
        db.add(user)
        await db.commit()
    AuditEventDispatcher.dispatch(
        UserLoginEvent(
            user_id=user.id, username=user.username, amr=[AMR.PASSWORD], idp="local", is_first_login=is_first_login
        )
    )
    logger.info("User logged in", user_id=str(user.id), username=user.username, amr=[AMR.PASSWORD], idp="local")

    # Set refresh cookie and CSRF cookie
    cookie_max_age = settings.jwt_refresh_token_lifetime_hours * 3600
    set_refresh_cookie(response, refresh_token_str, max_age=cookie_max_age)
    csrf_seed = generate_csrf_seed()
    set_csrf_cookie(response, csrf_seed, max_age=cookie_max_age)

    AuditEventDispatcher.dispatch(LoginAttemptEvent(username=username, method=LoginMethod.PASSWORD, user_id=user.id))
    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_access_token_lifetime_minutes * 60,
    )


def _extract_basic_credentials(request: Request) -> tuple[str, str] | None:
    """Extract client credentials from HTTP Basic Authorization header.

    Returns (client_id, client_secret) or None if header is absent/invalid.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in decoded:
        return None
    client_id, client_secret = decoded.split(":", 1)
    return client_id, client_secret


_DUMMY_ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def _dispatch_sa_login_failure(
    client_id: str | None,
    error_reason: LoginErrorReason,
    sa_id: UUID | None = None,
) -> NoReturn:
    """Dispatch an audit event for a failed service account login attempt and raise 401."""
    AuditEventDispatcher.dispatch(
        LoginAttemptEvent(
            username=client_id,
            method=LoginMethod.CLIENT_CREDENTIALS,
            error_type=error_reason,
            user_id=sa_id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )
    )
    raise AuthenticationRequiredError


def _validate_sa_credential(
    credential: ServiceAccountCredential,
    sa: ServiceAccount,
    client_id: str,
    client_secret: str,
) -> None:
    """Validate a service account and credential are usable, or raise 401.

    All checks are evaluated before any branching to prevent timing
    side-channels that could leak account status or existence.
    """
    secret_valid = verify_password(client_secret, credential.hashed_secret)
    if (
        not secret_valid
        and credential.old_hashed_secret
        and credential.old_secret_valid_until
        and datetime.now(UTC) < credential.old_secret_valid_until
    ):
        secret_valid = verify_password(client_secret, credential.old_hashed_secret)

    is_sa_disabled = sa.status != ServiceAccountStatus.ACTIVE
    is_cred_disabled = credential.status != ServiceAccountCredentialStatus.ACTIVE
    is_expired = credential.expires_at is not None and datetime.now(UTC) >= credential.expires_at

    if is_sa_disabled or is_cred_disabled or is_expired:
        _dispatch_sa_login_failure(client_id, LoginErrorReason.DISABLED_SERVICE_ACCOUNT, sa.id)
    elif not secret_valid:
        _dispatch_sa_login_failure(client_id, LoginErrorReason.BAD_PASSWORD, sa.id)


@router.post(
    "/token",
    operation_id="token",
    dependencies=[NO_PERMISSION],
    summary="OAuth 2.0 token endpoint",
    description="""
    Exchange client credentials for an access token (OAuth 2.0 client
    credentials grant, RFC 6749 Section 4.4).

    Credentials can be provided via HTTP Basic auth header or in the
    form-encoded request body.  Only `grant_type=client_credentials`
    is accepted.  No refresh token is issued.
    """,
    response_description="Access token issued",
    responses={
        400: {"description": "Unsupported grant type"},
        401: {"description": "Invalid client credentials"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()] = "",
    client_secret: Annotated[str, Form(json_schema_extra={"format": "password"})] = "",
) -> AccessTokenResponse:
    """Issue an access token via the OAuth 2.0 client credentials grant.

    Accepts credentials from either the HTTP Basic Authorization header
    or the form-encoded request body (per RFC 6749 Section 2.3).

    """
    if grant_type != "client_credentials":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported_grant_type",
        )

    basic_creds = _extract_basic_credentials(request)
    if basic_creds is not None:
        cred_client_id, cred_client_secret = basic_creds
    elif client_id and client_secret:
        cred_client_id, cred_client_secret = client_id, client_secret
    else:
        _dispatch_sa_login_failure(None, LoginErrorReason.UNKNOWN_USER)

    result = await db.exec(
        select(ServiceAccountCredential, ServiceAccount)
        .join(ServiceAccount, ServiceAccountCredential.service_account_id == ServiceAccount.id)  # type: ignore[arg-type]
        .where(ServiceAccountCredential.identifier == cred_client_id)
    )
    row = result.one_or_none()

    if row is None:
        verify_password(cred_client_secret, _DUMMY_ARGON2_HASH)
        _dispatch_sa_login_failure(cred_client_id, LoginErrorReason.UNKNOWN_USER)

    credential, sa = row

    _validate_sa_credential(credential, sa, cred_client_id, cred_client_secret)

    settings = get_settings()
    token_service = _get_token_service()
    access_token = token_service.create_access_token(
        subject_id=sa.id,
        username=sa.name,
        token_version=sa.token_version,
        credential_id=credential.id,
        principal_type=PrincipalType.SERVICE_ACCOUNT,
    )

    # Client-credentials has no Bearer JWT, so audit middleware leaves actor
    # ContextVars empty — attribute timestamp CRUD to the authenticating SA
    # (same AAP-83651 pattern as login/logout/OIDC).
    with actor_context(actor=sa):
        sa.last_authenticated_at = datetime.now(UTC)
        credential.last_used_at = datetime.now(UTC)
        db.add(sa)
        db.add(credential)
        await db.commit()

    AuditEventDispatcher.dispatch(
        LoginAttemptEvent(
            username=cred_client_id,
            method=LoginMethod.CLIENT_CREDENTIALS,
            user_id=sa.id,
            principal_type=PrincipalType.SERVICE_ACCOUNT,
        )
    )
    logger.info(
        "Service account authenticated",
        service_account_id=str(sa.id),
        client_id=cred_client_id,
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=settings.jwt_sa_access_token_lifetime_minutes * 60,
    )


@router.post(
    "/ws_ticket",
    operation_id="create_ws_ticket",
    dependencies=[NO_PERMISSION],
    summary="Exchange JWT for a WebSocket connection ticket",
    description="""
    Exchange a valid Bearer JWT for a short-lived, single-use opaque ticket.
    The client then connects to the WebSocket endpoint with ``?ticket=<ticket>``
    instead of passing the raw JWT in the query string, preventing token leakage
    in server/proxy logs and browser history.
    """,
    response_description="Single-use WebSocket ticket",
    responses={
        401: {"description": "Invalid or missing authentication"},
        403: {
            "description": "Service accounts cannot obtain WebSocket tickets",
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/ErrorData"},
                },
            },
        },
    },
)
async def create_ws_ticket(
    payload: Annotated[TokenPayload, Depends(get_token_payload)],
) -> WebSocketTicketResponse:
    """Issue a single-use WebSocket connection ticket."""
    if payload.token_type == "service_account":  # noqa: S105
        raise ServiceAccountWSTicketError(service_account_id=payload.sub)

    from syntara.core.websocket.ticket import get_ticket_client  # noqa: PLC0415

    client = get_ticket_client()
    ticket, ttl = await client.issue_ticket(
        user_id=UUID(payload.sub),
        username=payload.preferred_username or payload.sub,
        email=payload.email,
        first_name=payload.given_name or payload.name,
        last_name=payload.family_name,
    )
    return WebSocketTicketResponse(ticket=ticket, expires_in=ttl)


@router.post(
    "/csrf_token",
    operation_id="get_csrf_token",
    summary="Get CSRF form token",
    description="""
    Return the CSRF form token derived from the session's CSRF seed cookie.

    The SPA calls this once after login or OIDC redirect to obtain the
    form token, which it then sends in the ``X-CSRF-Token`` header on
    subsequent state-changing requests (refresh, logout).
    """,
    response_description="CSRF form token",
    responses={
        403: {"description": "CSRF cookie missing — not authenticated via cookie flow"},
    },
)
async def get_csrf_token(request: Request) -> CsrfTokenResponse:
    """Return the CSRF form token derived from the session's seed cookie."""
    seed = request.cookies.get(CSRF_COOKIE_NAME)
    if not seed:
        raise CSRFValidationError(ERR_COOKIE_MISSING, error_code=CSRFErrorCode.COOKIE_MISSING)
    return CsrfTokenResponse(csrf_token=derive_csrf_form_token(seed))


@router.post(
    "/refresh",
    operation_id="refresh_token",
    dependencies=[NO_PERMISSION],
    summary="Refresh access token",
    description="""
    Exchange a valid refresh token for a new access token.

    The refresh token is read from the ``ao_refresh_token`` HttpOnly cookie.
    It is not rotated — the same refresh token remains valid for its entire
    lifetime (default 8 hours from login).  The cookie is re-set on every
    successful refresh so the ``max-age`` counter restarts.
    """,
    response_description="New access token issued",
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def refresh_token(
    request: Request,  # noqa: ARG001
    response: Response,  # noqa: ARG001
    payload: Annotated[TokenPayload, Depends(get_refresh_token)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    """Refresh access token using the refresh token cookie.

    The refresh token is validated but **not rotated** — this is an
    intentional architectural decision.  The fixed expiration on the
    refresh token acts as a hard session boundary, forcing users to
    re-authenticate with their IdP when the token expires.  This
    ensures group memberships are refreshed from the identity provider
    on a predictable cadence.

    If refresh-token rotation is added in the future, the *original*
    token's expiration timestamp must be preserved on every rotated
    successor so that the hard session expiration remains enforced.

    Args:
        request: FastAPI request object
        response: FastAPI response object
        payload: Decoded and validated refresh-token payload (extracted,
            decoded, and checked for global revocation by the
            ``get_refresh_token`` dependency)
        db: Database session

    Returns:
        Access token response

    Raises:
        AuthenticationRequiredError: If refresh token is missing or invalid
        TokenExpiredError: If refresh token has expired
        RefreshTokenRevokedError: If refresh token has been revoked
        TokenGloballyRevokedError: If refresh token was issued before the
            global revocation timestamp

    """
    settings = get_settings()
    token_service = _get_token_service()

    # Check refresh token in session store (single JOIN query for session + token_version)
    try:
        store = create_session_store(db)
        if not payload.jti:
            raise RefreshTokenRevokedError

        session_result = await store.get_with_token_version(payload.jti)
        if session_result is None:
            logger.warning("Refresh token not found in session store", jti=payload.jti)
            raise RefreshTokenRevokedError

        session, token_version = session_result

        # Load user from database to get current info
        result = await db.exec(select(User).filter(User.id == payload.sub))  # type: ignore[arg-type]
        user = result.one_or_none()

        if not user:
            logger.warning("User not found for refresh token", user_id=payload.sub)
            raise AuthenticationRequiredError

        if not user.is_enabled:
            from syntara.auth.audit.disabled_user_rejection import (  # noqa: PLC0415
                DisabledUserRejectionEvent,
                RejectionContext,
            )

            AuditEventDispatcher.dispatch(
                DisabledUserRejectionEvent(
                    user_id=str(payload.sub),
                    context=RejectionContext.TOKEN_REFRESH,
                    user_name=payload.preferred_username,
                )
            )
            logger.warning("Inactive user attempted token refresh", user_id=payload.sub)
            raise AuthenticationRequiredError

        username = user.username
        amr = session.amr or payload.amr or ["pwd"]
        idp = session.idp or payload.idp or "local"

        user_group_names = await _get_user_group_names(db, user.id)

        access_token = token_service.create_access_token(
            subject_id=user.id,
            username=username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            amr=amr,
            idp=idp,
            groups=user_group_names,
            token_version=token_version,
        )

        AuditEventDispatcher.dispatch(
            SessionLifecycleEvent(
                action=SessionAction.REFRESH,
                user_id=user.id,
                username=user.username,
                jti=payload.jti,
                idp=idp,
            )
        )

        logger.info(
            "Token refreshed successfully",
            user_id=str(user.id),
            jti=payload.jti,
        )

        return AccessTokenResponse(
            access_token=access_token,
            expires_in=settings.jwt_access_token_lifetime_minutes * 60,
        )
    except SQLAlchemyError as exc:
        logger.exception("Session store failed during refresh", error=str(exc))
        raise SessionStoreUnavailableError from exc


def _build_rp_logout_url(
    end_session_endpoint: str,
    id_token_hint: str | None,
    post_logout_redirect_uri: str,
) -> str:
    """Build OIDC RP-initiated logout URL per OpenID Connect RP-Initiated Logout 1.0.

    Args:
        end_session_endpoint: IdP's end_session_endpoint from discovery
        id_token_hint: The ID token to pass as hint (recommended by spec)
        post_logout_redirect_uri: URI to redirect to after IdP logout

    Returns:
        Full logout URL with encoded query parameters

    """
    params = {}

    if id_token_hint:
        params["id_token_hint"] = id_token_hint

    if post_logout_redirect_uri:
        params["post_logout_redirect_uri"] = post_logout_redirect_uri

    if params:
        return f"{end_session_endpoint}?{urlencode(params)}"
    return end_session_endpoint


async def _resolve_end_session_endpoint(config: OIDCConfiguration) -> str | None:
    """Resolve the end_session_endpoint, falling back to OIDC discovery.

    Prefers the statically configured value. If absent and auto_discovery
    is enabled, fetches the OIDC discovery document to find it.
    """
    if config.end_session_endpoint:
        return str(config.end_session_endpoint)

    if not config.auto_discovery:
        return None

    try:
        oidc_service = OIDCService()
        discovery = await oidc_service.fetch_discovery_config(
            str(config.issuer_url), disable_tls_verify=config.disable_tls_verify
        )
        return discovery.get("end_session_endpoint")
    except OIDCError:
        logger.warning("Failed to discover end_session_endpoint for RP logout")
        return None


async def _maybe_rp_logout(
    db: AsyncSession,
    session_info: SessionInfo | None,
    post_logout_redirect_uri: str,
) -> dict[str, str] | None:
    """Build RP-initiated logout info if applicable, else return None.

    Returns a dict with ``redirect_url`` (happy path) or ``auth_error``
    (failsafe when the IdP's end-session endpoint can't be resolved).
    The caller always includes ``detail`` before returning to the client.

    Args:
        db: Database session
        session_info: Session metadata (None for local sessions)
        post_logout_redirect_uri: Where to redirect after IdP logout
            (caller-provided post_logout_redirect_uri validated against
            CORS origins, or the global setting as fallback)

    """
    if not session_info or not session_info.idp_id:
        return None

    result = await db.exec(
        select(IdentityProvider).filter(
            IdentityProvider.id == UUID(session_info.idp_id),  # type: ignore[arg-type]
        )
    )
    provider = result.one_or_none()

    if (
        not provider
        or not isinstance(provider.configuration, OIDCConfiguration)
        or not provider.configuration.enable_rp_initiated_logout
    ):
        return None

    end_session_endpoint = await _resolve_end_session_endpoint(provider.configuration)
    if not end_session_endpoint:
        logger.warning(
            "RP-initiated logout enabled but end_session_endpoint could not be resolved",
            provider=provider.name,
        )
        return {"auth_error": OIDCErrorCode.IDP_LOGOUT_FAILED}

    # Decrypt the ID token hint if available
    decrypted_id_token_hint = None
    if session_info.id_token_hint:
        try:
            enc_key = key_from_string(get_encryption_key().get_secret_value())
            encryptor = SecretEncryptor(enc_key)
            decrypted_id_token_hint = encryptor.decrypt_field(session_info.id_token_hint, "session", "id_token_hint")
        except (RuntimeError, ValueError):
            logger.warning("Failed to decrypt id_token_hint for RP logout", provider=provider.name)

    logout_url = _build_rp_logout_url(
        end_session_endpoint=end_session_endpoint,
        id_token_hint=decrypted_id_token_hint,
        post_logout_redirect_uri=post_logout_redirect_uri,
    )

    logger.info("RP-initiated logout URL built", provider=provider.name, idp=session_info.idp)
    return {"redirect_url": logout_url}


@router.post(
    "/logout",
    summary="Terminate session",
    operation_id="logout",
    dependencies=[NO_PERMISSION],
    description="""
    Terminate the current session by revoking the refresh token.

    The refresh token is read from the ``ao_refresh_token`` HttpOnly cookie
    and revoked in the session store.  The cookie is cleared in the response.
    The associated access token remains valid until it expires (up to 15
    minutes) since access tokens are stateless JWTs validated without a
    server round-trip.
    """,
    responses={
        401: {"description": "Invalid or expired refresh token"},
    },
    response_model=None,
)
@audit(EventCategory.SECURITY_EVENT)
async def logout(
    payload: Annotated[TokenPayload, Depends(get_refresh_token)],
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    post_logout_redirect_uri: str | None = None,
) -> dict[str, str]:
    """Logout by revoking the refresh token session.

    The refresh token is revoked in the session store and the cookie is cleared.
    Always returns JSON. For OIDC sessions with RP-initiated logout
    enabled, the response includes a ``redirect_url`` the frontend
    should navigate to (``window.location.href``). If the IdP's
    end-session endpoint cannot be resolved, returns ``auth_error``
    instead so the frontend can warn the user.

    Args:
        payload: Decoded and validated refresh-token payload (extracted,
            decoded, and checked for global revocation by the
            ``get_refresh_token`` dependency)
        request: FastAPI request object (for Referer origin extraction)
        response: FastAPI response object (cookie cleared here)
        db: Database session
        post_logout_redirect_uri: Optional post-logout redirect URL (validated against CORS origins)

    Returns:
        JSON with ``detail`` and optionally ``redirect_url`` or ``auth_error``

    Raises:
        AuthenticationRequiredError: If refresh token cookie is missing or invalid
        TokenGloballyRevokedError: If refresh token was issued before the
            global revocation timestamp

    """
    settings = get_settings()

    if not payload.jti:
        clear_refresh_cookie(response)
        raise AuthenticationRequiredError

    # Validate post_logout_redirect_uri against CORS origins (same as login flow)
    origin = _extract_referer_origin(request)
    post_logout_uri = (
        _safe_redirect_url(post_logout_redirect_uri, origin=origin)
        if post_logout_redirect_uri
        else settings.post_logout_redirect_uri
    )

    # Get session metadata before revoking (needed for RP-logout)
    session_metadata = None
    try:
        store = create_session_store(db)
        session_metadata = await store.get(payload.jti)

        # Logout authenticates via refresh cookie only — audit middleware does
        # not seed actor ContextVars from Bearer. Attribute the token_version
        # CRUD event from the validated refresh payload (AAP-83651).
        logout_actor = AuditActorContext(
            actor_id=UUID(payload.sub),
            actor_username=payload.preferred_username,
            actor_type=PrincipalType.USER,
        )
        with actor_context(actor=logout_actor):
            await store.increment_token_version(UUID(payload.sub))
            revoked = await store.revoke(payload.jti)
            await db.commit()

        if revoked:
            logger.info(
                "User logged out successfully",
                user_id=payload.sub,
                jti=payload.jti,
            )
        else:
            logger.info(
                "Logout for already-expired session",
                user_id=payload.sub,
                jti=payload.jti,
            )
    except SQLAlchemyError as exc:
        AuditEventDispatcher.dispatch(
            SessionLifecycleEvent(
                action=SessionAction.REVOKE,
                user_id=UUID(payload.sub),
                username=payload.preferred_username,
                jti=payload.jti,
                error_type=type(exc).__name__,
            )
        )
        logger.exception("Session store failed during logout", error=str(exc))
        raise SessionStoreUnavailableError from exc
    AuditEventDispatcher.dispatch(
        SessionLifecycleEvent(
            action=SessionAction.REVOKE, user_id=UUID(payload.sub), username=payload.preferred_username, jti=payload.jti
        )
    )

    # Clear the refresh and CSRF cookies
    clear_refresh_cookie(response)
    clear_csrf_cookie(response)

    # Build base response; merge RP-logout fields when applicable
    result: dict[str, str] = {"detail": "Successfully logged out"}

    rp_info = await _maybe_rp_logout(db, session_metadata, post_logout_uri)
    if rp_info:
        result.update(rp_info)

    return result


@router.get(
    "/me",
    operation_id="get_current_user",
    dependencies=[NO_PERMISSION],
    summary="Get current user",
    description="""
    Returns information about the currently authenticated user
    from the access token claims and session metadata.
    """,
    response_description="Current user information",
    responses={
        401: {"description": "Invalid or missing authentication"},
    },
)
@audit(EventCategory.USER_ACTION)
async def get_me(
    request: Request,
    payload: Annotated[TokenPayload, Depends(get_token_payload)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserInfo:
    """Get current authenticated user information from token claims."""
    rp_logout_enabled = False

    raw_refresh_token = get_refresh_token_from_cookie(request)
    if raw_refresh_token:
        try:
            token_service = _get_token_service()
            token_payload = token_service.decode_token(raw_refresh_token, token_type="refresh")  # noqa: S106

            if token_payload.jti:
                store = create_session_store(db)
                session_metadata = await store.get(token_payload.jti)
                if session_metadata:
                    rp_logout_enabled = session_metadata.rp_logout_enabled
        except (InvalidTokenError, RuntimeError, ValueError):
            logger.debug("Could not determine RP-logout status for /auth/me")

    return UserInfo(
        id=payload.sub,
        username=payload.preferred_username or "",
        email=payload.email,
        groups=payload.groups or [],
        rp_logout_enabled=rp_logout_enabled,
    )


@router.get(
    "/providers",
    operation_id="list_auth_providers",
    dependencies=[NO_PERMISSION],
    summary="List enabled identity providers",
    description="""
    Returns a list of enabled identity providers for the login page.
    This is a public endpoint that does not require authentication.
    Only returns provider id, name, and type — no secrets or configuration details.
    """,
    response_description="List of enabled identity providers",
)
@audit(EventCategory.USER_ACTION)
async def list_auth_providers(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthProvidersResponse:
    """List enabled identity providers for the login page. Public endpoint."""
    result = await db.exec(
        select(IdentityProvider).filter(
            col(IdentityProvider.enabled) == True,  # noqa: E712
        )
    )
    providers = result.all()

    return AuthProvidersResponse(
        resources=[
            AuthProviderInfo(
                id=str(p.id),
                name=p.name,
                provider_type=p.configuration.provider_type if p.configuration else "oidc",
                provider_template=getattr(p.configuration, "idp_type", None) if p.configuration else None,
            )
            for p in providers
        ]
    )


@router.get(
    "/oidc/authorize",
    operation_id="oidc_authorize",
    dependencies=[NO_PERMISSION],
    summary="Initiate OIDC login",
    description=(
        "Initiates the OIDC authorization code flow. Redirects the user's browser\n"
        "to the identity provider's authorization endpoint.\n\n"
        "This is a public endpoint (no authentication required). On any error it\n"
        "redirects to the frontend login page with an `auth_error` query parameter\n"
        "instead of returning a JSON error response.\n"
    ),
    responses={
        302: {"description": "Redirect to identity provider or frontend on error"},
    },
)
@audit(EventCategory.SECURITY_EVENT)
async def oidc_authorize(
    provider_id: Annotated[UUID, Query(description="UUID of the identity provider to use")],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    redirect_to: Annotated[str | None, Query(description="URL to redirect to after successful login")] = None,
    flow: Literal["link", "test_signin"] | None = None,
) -> RedirectResponse:
    """Initiate OIDC login by redirecting to the provider's authorization endpoint."""
    origin = _extract_referer_origin(request)

    try:
        result = await _build_oidc_authorize_redirect(provider_id, request, db, redirect_to, flow=flow)
        AuditEventDispatcher.dispatch(OIDCFlowEvent(provider_id=provider_id, stage=OIDCStage.AUTHORIZE))
        return result
    except (OIDCError, OIDCCallbackError) as e:
        AuditEventDispatcher.dispatch(
            OIDCFlowEvent(provider_id=provider_id, stage=OIDCStage.AUTHORIZE, error_type=type(e).__name__)
        )
        logger.warning("OIDC authorize failed, redirecting to login", provider_id=str(provider_id), error=str(e))
        error_code = e.error_code if isinstance(e, OIDCCallbackError) else OIDCErrorCode.AUTH_FAILED
        return _build_authorize_error_redirect(origin, redirect_to, flow, error_code)
    except Exception as e:
        AuditEventDispatcher.dispatch(
            OIDCFlowEvent(provider_id=provider_id, stage=OIDCStage.AUTHORIZE, error_type=type(e).__name__)
        )
        logger.exception("Unexpected error during OIDC authorize", provider_id=str(provider_id))
        return _build_authorize_error_redirect(origin, redirect_to, flow, OIDCErrorCode.DISCOVERY_FAILED)


async def _verify_idp_test_permission(request: Request, db: AsyncSession) -> None:
    """Verify the current user has identity-provider:test permission.

    Used by the test-signin flow which is a browser redirect (not a REST endpoint),
    so we can't use the standard ``Depends(PermissionChecker(...))`` pattern.
    Instead, we manually decode the refresh token and run the authz check.
    """
    raw_token = get_refresh_token_from_cookie(request)
    if not raw_token:
        msg = "Authentication required for test sign-in"
        raise OIDCError(msg)
    token_service = _get_token_service()
    try:
        payload = token_service.decode_token(raw_token, token_type="refresh")  # noqa: S106
    except Exception as e:
        msg = "Authentication required for test sign-in"
        raise OIDCError(msg) from e

    # Verify the session hasn't been revoked
    if payload.jti:
        store = create_session_store(db)
        session = await store.get(payload.jti)
        if session is None:
            msg = "Session expired or revoked. Please log in again."
            raise OIDCError(msg)

    # Load the user for authz metadata
    user = await _find_non_deleted_user(db, UUID(str(payload.sub)))
    if not user:
        msg = "Authentication required for test sign-in"
        raise OIDCError(msg)

    # Run the same authz check as the identity-provider:test permission
    evaluator = get_authz_evaluator(request)
    authz_result = await authorize(
        db,
        evaluator,
        AuthzRequest(
            user_id=user.id,
            action="test",
            resource_type="identity-provider",
            resource_id="",
            resource_project="",
            user_labels=user.labels,
            user_metadata=user.authz_metadata,
        ),
    )
    if not authz_result.allowed:
        msg = "Not authorized to perform test sign-in"
        raise OIDCError(msg)


async def _build_oidc_authorize_redirect(
    provider_id: UUID,
    request: Request,
    db: AsyncSession,
    redirect_to: str | None,
    *,
    flow: Literal["link", "test_signin"] | None = None,
) -> RedirectResponse:
    """Build the OIDC authorization redirect. Raises on any failure."""
    # For link flow, verify the user is authenticated via refresh token cookie
    flow_type: str | None = None
    link_user_id: str | None = None
    link_session_jti: str | None = None
    if flow == "test_signin":
        # Test sign-in requires identity-provider:test permission (admin only)
        await _verify_idp_test_permission(request, db)
        flow_type = "test_signin"
    elif flow == "link":
        raw_token = get_refresh_token_from_cookie(request)
        if not raw_token:
            msg = "Authentication required to link identity"
            raise OIDCError(msg)
        token_service = _get_token_service()
        try:
            payload = token_service.decode_token(raw_token, token_type="refresh")  # noqa: S106
        except Exception as e:
            msg = "Authentication required to link identity"
            raise OIDCError(msg) from e
        # Verify session is active
        store = create_session_store(db)
        session = await store.get(payload.jti) if payload.jti else None
        if session is None:
            msg = "Session expired. Please log in again."
            raise OIDCError(msg)
        flow_type = "link"
        link_user_id = str(payload.sub)
        link_session_jti = payload.jti

    oidc_service = OIDCService()
    provider = await _load_enabled_provider(db, provider_id)
    config = provider.configuration

    discovery = await _get_oidc_endpoints(oidc_service, config)

    nonce = oidc_service.generate_nonce()
    code_verifier, code_challenge = oidc_service.generate_pkce()

    origin = _extract_referer_origin(request)
    safe_redirect = _safe_redirect_url(redirect_to, origin=origin) if redirect_to else None

    # Encode OIDC flow state as a signed JWT (no server-side storage)
    state = oidc_service.store_oidc_state(
        provider_id=provider.id,
        nonce=nonce,
        code_verifier=code_verifier,
        redirect_to=safe_redirect,
        origin=origin,
        flow_type=flow_type,
        user_id=link_user_id,
        session_jti=link_session_jti,
    )

    redirect_uri = str(config.redirect_uri)

    auth_url = oidc_service.build_authorization_url(
        authorization_endpoint=discovery["authorization_endpoint"],
        client_id=config.client_id,
        redirect_uri=redirect_uri,
        scopes=config.scopes,
        state=state,
        nonce=nonce,
        code_challenge=code_challenge,
    )

    parsed_auth = urlparse(auth_url)
    if parsed_auth.scheme not in ("http", "https"):
        msg = "OIDC authorization endpoint has invalid URL scheme"
        raise OIDCError(msg)

    logger.info("Redirecting to OIDC provider", provider_id=str(provider_id), provider_name=provider.name)

    return RedirectResponse(url=auth_url, status_code=302)


async def _get_oidc_endpoints(
    oidc_service: OIDCService,
    config: IdentityProviderConfigurationTypes,
) -> dict[str, Any]:
    """Get OIDC endpoints via auto-discovery or from manual configuration."""
    if config.auto_discovery:
        return await oidc_service.fetch_discovery_config(
            str(config.issuer_url), disable_tls_verify=config.disable_tls_verify
        )

    # Manual endpoints — validate required fields are present
    if not config.authorization_endpoint or not config.token_endpoint or not config.jwks_uri:
        msg = "Manual OIDC configuration requires authorization_endpoint, token_endpoint, and jwks_uri"
        raise OIDCError(msg)

    return {
        "authorization_endpoint": str(config.authorization_endpoint),
        "token_endpoint": str(config.token_endpoint),
        "jwks_uri": str(config.jwks_uri),
        "issuer": str(config.issuer_url),
        "userinfo_endpoint": str(config.userinfo_endpoint) if config.userinfo_endpoint else "",
        "end_session_endpoint": str(config.end_session_endpoint) if config.end_session_endpoint else "",
    }


async def _load_enabled_provider(db: AsyncSession, provider_id: str | UUID) -> IdentityProvider:
    """Load an enabled identity provider or raise."""
    result = await db.exec(
        select(IdentityProvider).filter(
            IdentityProvider.id == provider_id,  # type: ignore[arg-type]  # SQLModel UUID comparison
            col(IdentityProvider.enabled) == True,  # noqa: E712
        )
    )
    provider = result.one_or_none()
    if not provider:
        # Intentionally use a generic message to avoid leaking whether a provider exists
        raise OIDCError(_OIDC_ERR_PROVIDER_UNAVAILABLE)
    return provider


async def _load_provider_config(db: AsyncSession, provider: IdentityProvider) -> OIDCConfiguration:
    """Load provider configuration with decrypted secrets for OIDC flows.

    Uses SecretService directly rather than IdentityProviderService.get_decrypted_config()
    because the OIDC callback is unauthenticated — there is no current User to satisfy
    BaseService.__init__. For authenticated flows, use IdentityProviderService instead.
    """
    config_data = provider.configuration.model_dump()
    if provider.secret_id:
        secret_service = create_secret_service(db)
        secrets = await secret_service.retrieve_secret(provider.secret_id)
        config_data = {**config_data, **secrets}
    return OIDCConfiguration.model_validate(config_data)


async def _exchange_and_validate_tokens(
    oidc_service: OIDCService,
    discovery: dict[str, Any],
    config: IdentityProviderConfigurationTypes,
    redirect_uri: str,
    code: str,
    code_verifier: str,
    nonce: str,
) -> tuple[dict[str, str | None], dict[str, Any], str]:
    """Exchange code for tokens, validate ID token, return user claims and raw claims.

    If the ID token is missing key user claims (email, name, preferred_username)
    and a userinfo endpoint is available, fetches additional claims from the
    userinfo endpoint per OIDC Core §5.3.  ID token claims take precedence.

    Returns:
        Tuple of (extracted user_claims, raw merged claims for JMESPath group mapping, id_token_raw)

    """
    token_response = await oidc_service.exchange_code_for_tokens(
        token_endpoint=discovery["token_endpoint"],
        code=code,
        redirect_uri=redirect_uri,
        client_id=config.client_id,
        client_secret=config.client_secret or "",
        code_verifier=code_verifier,
        disable_tls_verify=config.disable_tls_verify,
    )

    id_token_raw = token_response.get("id_token")
    if not id_token_raw:
        logger.warning("No id_token in token response")
        msg = "Identity provider did not return an ID token"
        raise OIDCError(msg)

    id_token_claims = oidc_service.validate_id_token(
        id_token=id_token_raw,
        jwks_uri=discovery["jwks_uri"],
        issuer=discovery["issuer"],
        client_id=config.client_id,
        nonce=nonce,
        disable_tls_verify=config.disable_tls_verify,
    )

    logger.debug("Raw ID token claims from IdP", claims=list(id_token_claims.keys()))

    user_claims = oidc_service.extract_user_claims(id_token_claims, config.claim_mapping)

    # Start with ID token claims as the raw merged set
    raw_merged_claims: dict[str, Any] = dict(id_token_claims)

    # Fetch userinfo when key claims are missing OR when group mapping is configured
    # (group claims like aap_teams are often only available from the userinfo endpoint)
    userinfo_endpoint = discovery.get("userinfo_endpoint")
    access_token = token_response.get("access_token")
    missing_claims = not user_claims.get("email") or not user_claims.get("name")
    has_group_mapping = config.group_jmespath_expression is not None

    if (missing_claims or has_group_mapping) and userinfo_endpoint and access_token:
        try:
            userinfo = await oidc_service.fetch_userinfo(
                userinfo_endpoint, access_token, disable_tls_verify=config.disable_tls_verify
            )
            # Verify sub claim matches per OIDC Core §5.3.2
            if userinfo.get("sub") != id_token_claims.get("sub"):
                logger.warning("Userinfo sub mismatch, discarding userinfo")
            else:
                userinfo_claims = oidc_service.extract_user_claims(userinfo, config.claim_mapping)
                # ID token claims take precedence per OIDC Core §5.3.2
                for key, value in userinfo_claims.items():
                    if not user_claims.get(key) and value:
                        user_claims[key] = value
                # Merge raw userinfo into merged claims (ID token takes precedence)
                for key, value in userinfo.items():
                    if key not in raw_merged_claims:
                        raw_merged_claims[key] = value
                logger.debug("Supplemented user claims from userinfo endpoint")
        except OIDCError:
            logger.warning("Failed to fetch userinfo, proceeding with ID token claims only")

    return user_claims, raw_merged_claims, id_token_raw


async def _find_non_deleted_user(db: AsyncSession, user_id: UUID) -> User | None:
    """Load a non-deleted user by ID, or return None if deleted/missing."""
    result = await db.exec(
        select(User).filter(
            User.id == user_id,  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.one_or_none()


async def _load_active_user(db: AsyncSession, user_id: UUID) -> User:
    """Load a non-deleted, active user or raise OIDCError."""
    user = await _find_non_deleted_user(db, user_id)
    if not user:
        msg = "Linked user account has been deleted. Contact your administrator."
        raise OIDCError(msg)
    if not user.is_enabled:
        logger.warning("OIDC login blocked: user account is deactivated", user_id=str(user_id))
        raise OIDCError(_OIDC_ERR_AUTH_FAILED)
    return user


def _validate_sub_claim(user_claims: dict[str, str | None]) -> str:
    """Extract and validate the OIDC sub claim, returning it if valid."""
    sub = user_claims.get("sub")
    if not sub:
        logger.warning("Missing sub claim in OIDC token")
        msg = "Identity provider did not return a subject identifier"
        raise OIDCError(msg)
    if len(sub) > SUBJECT_MAX_LENGTH:
        logger.warning(
            "OIDC sub claim exceeds maximum length",
            length=len(sub),
            max_length=SUBJECT_MAX_LENGTH,
        )
        msg = "Identity provider returned an identifier that exceeds the maximum supported length"
        raise OIDCError(msg)
    return sub


async def _find_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Find a non-deleted user by email address."""
    result = await db.exec(
        select(User).filter(
            User.email == email,  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.one_or_none()


async def _create_identity_with_race_handling(
    db: AsyncSession,
    identity_service: UserIdentityService,
    user: User,
    provider_id: UUID,
    issuer: str,
    sub: str,
) -> tuple[User, UserIdentity]:
    """Create an identity link, handling race conditions on the unique constraint.

    Returns:
        Tuple of (User, UserIdentity) for session tracking

    """
    try:
        async with db.begin_nested():
            identity = await identity_service.create_identity(
                user_id=user.id,
                identity_provider_id=provider_id,
                issuer=issuer,
                subject=sub,
            )
            identity.last_used_at = datetime.now(UTC)
            db.add(identity)
    except IntegrityError as e:
        existing = await identity_service.find_by_issuer_and_subject(issuer, sub)
        if existing:
            # Re-load user from fresh session state after rollback
            user = await _load_active_user(db, existing.user_id)
            return (user, existing)
        msg = "Unable to sign in. Contact your administrator."
        raise OIDCError(msg) from e
    except DataError as e:
        msg = "Unable to sign in. Contact your administrator."
        raise OIDCError(msg) from e
    # Refresh user to ensure it's attached to the current session state
    await db.refresh(user)
    return (user, identity)


async def _try_resolve_linked_identity(
    db: AsyncSession,
    identity_service: UserIdentityService,
    issuer: str,
    sub: str,
) -> tuple[User, UserIdentity] | None:
    """Look up an existing identity link and return the linked user if valid.

    Returns None if no usable link exists (identity missing, or linked user deleted).
    """
    identity = await identity_service.find_by_issuer_and_subject(issuer, sub)
    if not identity:
        return None

    linked_user = await _find_non_deleted_user(db, identity.user_id)
    if linked_user:
        if not linked_user.is_enabled:
            logger.warning("OIDC login blocked: user account is deactivated", user_id=str(identity.user_id))
            raise OIDCError(_OIDC_ERR_AUTH_FAILED)
        identity.last_used_at = datetime.now(UTC)
        db.add(identity)
        return (linked_user, identity)

    logger.warning(
        "Removing stale identity for deleted user",
        identity_id=str(identity.id),
        deleted_user_id=str(identity.user_id),
    )
    await identity_service.delete_identity(identity.id, force=True)
    return None


async def _resolve_oidc_user(
    db: AsyncSession,
    user_claims: dict[str, str | None],
    provider: IdentityProvider,
) -> tuple[User, UserIdentity]:
    """Resolve a user from OIDC claims using federated identity linking.

    1. Look up UserIdentity by (issuer, sub) — if found, return linked user.
    2. If an existing user matches by email — block login and direct to self-service linking.
    3. If no match — auto-create new user + identity.

    Returns:
        Tuple of (User, UserIdentity) for session tracking

    """
    raw_email = user_claims.get("email")
    email = (
        raw_email.strip().lower() if isinstance(raw_email, str) and EMAIL_PATTERN.fullmatch(raw_email.strip()) else None
    )

    sub = _validate_sub_claim(user_claims)

    # Cache provider attributes before any DB rollback can expire the ORM object
    provider_name = provider.name
    provider_id = provider.id
    issuer = str(provider.configuration.issuer_url)
    identity_service = UserIdentityService(db)

    for attempt in range(2):
        # Step 1: Look up by (issuer, sub)
        resolved = await _try_resolve_linked_identity(db, identity_service, issuer, sub)
        if resolved:
            return resolved

        # Step 2: Check if a user with the same email already exists.
        # Block login and direct the user to self-service identity linking.
        if email:
            existing_user = await _find_user_by_email(db, email)
            if existing_user:
                if attempt == 0:
                    # On first attempt, the email match may be the winner from
                    # a concurrent race — retry to pick up their identity link.
                    logger.info("Retrying user resolution after email collision", sub=sub)
                    continue
                logger.warning(
                    "Login blocked: email already associated with another account",
                    existing_user_id=str(existing_user.id),
                    provider=provider_name,
                )
                msg = (
                    "This email is already associated with an existing account. "
                    "Please sign in with your original authentication method and "
                    "link this identity provider via the Identities tab on your user profile page."
                )
                raise OIDCError(msg, error_code=OIDCErrorCode.EMAIL_ALREADY_LINKED)

        # Step 3: No identity or email match — create new user.
        try:
            user = await _auto_create_user(db, user_claims, provider_name, email=email)
        except OIDCError:
            if attempt == 1:
                raise
            logger.info("Retrying user resolution after concurrent creation", sub=sub)
            continue

        return await _create_identity_with_race_handling(db, identity_service, user, provider_id, issuer, sub)

    # Should not be reached — the loop either returns or raises
    msg = "Unable to sign in. Contact your administrator."
    raise OIDCError(msg)


async def _is_username_taken(db: AsyncSession, value: str) -> bool:
    """Check if a username is already taken by a non-deleted user."""
    result = await db.exec(
        select(User).filter(
            User.username == value,  # type: ignore[arg-type]
            User.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.one_or_none() is not None


async def _auto_create_user(
    db: AsyncSession,
    user_claims: dict[str, str | None],
    provider_name: str,
    *,
    email: str | None = None,
) -> User:
    """Auto-create a user from OIDC claims."""
    email = email.strip().lower() if email else None

    if email and len(email) > FieldLimits.NAME_MAX_LENGTH:
        logger.warning("OIDC email exceeds maximum length", length=len(email), provider=provider_name)
        msg = "Email address exceeds maximum length"
        raise OIDCError(msg)

    preferred_username = (user_claims.get("preferred_username") or "").strip()
    if not preferred_username:
        if email:
            preferred_username = email.split("@", maxsplit=1)[0]
        else:
            preferred_username = user_claims.get("sub") or secrets.token_hex(8)
    preferred_username = preferred_username.lower()

    raw_given_name = strip_control_chars((user_claims.get("given_name") or "").strip())
    raw_family_name = strip_control_chars((user_claims.get("family_name") or "").strip())
    raw_name = strip_control_chars((user_claims.get("name") or "").strip())

    if raw_given_name:
        first_name = raw_given_name[: FieldLimits.NAME_MAX_LENGTH]
        last_name = raw_family_name[: FieldLimits.NAME_MAX_LENGTH] if raw_family_name else None
    elif raw_name:
        first_name = raw_name[: FieldLimits.NAME_MAX_LENGTH]
        last_name = None
    else:
        first_name = preferred_username[: FieldLimits.NAME_MAX_LENGTH]
        last_name = None

    # Truncate username to leave room for the random suffix (hyphen + 16 hex chars)
    preferred_username = preferred_username[: FieldLimits.NAME_MAX_LENGTH - 17]

    # Resolve unique username: try preferred, then append a random suffix
    username = preferred_username
    if await _is_username_taken(db, username):
        random_suffix = secrets.token_hex(8)
        username = f"{preferred_username}-{random_suffix}"
        if await _is_username_taken(db, username):
            logger.warning("OIDC username collision", username=username)
            msg = "Username already taken. Contact your administrator."
            raise OIDCError(msg)

    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=None,
        auth_type=AuthType.FEDERATED,
        is_enabled=True,
    )
    try:
        async with db.begin_nested():
            db.add(user)
            await db.flush()
    except IntegrityError as e:
        constraint = getattr(e.orig, "constraint_name", None) if e.orig else None
        logger.warning(
            "OIDC auto-create user failed due to integrity constraint",
            constraint=constraint or "unknown",
            provider=provider_name,
        )
        msg = "Unable to create account. Contact your administrator."
        raise OIDCError(msg) from e
    logger.info("Auto-created user from OIDC", user_id=str(user.id), username=username, provider=provider_name)

    await _grant_authenticated_group(db, user)

    return user


async def _grant_authenticated_group(db: AsyncSession, user: User) -> None:
    """Add an auto-created user to the authenticated group and emit a membership audit."""
    auth_group = (
        await db.exec(
            select(Group).where(Group.name == AUTHENTICATED_GROUP_NAME, Group.deleted_at.is_(None))  # type: ignore[union-attr]
        )
    ).first()
    if not auth_group:
        msg = f"Required built-in group '{AUTHENTICATED_GROUP_NAME}' is missing from the database"
        raise RuntimeError(msg)
    await db.exec(sa_insert(user_groups).values(user_id=user.id, group_id=auth_group.id))
    AuditEventDispatcher.dispatch(
        GroupMembershipEvent(
            user_id=user.id,
            username=user.username,
            group_id=auth_group.id,
            group_name=auth_group.name,
            action="added",
        ),
    )


# Log-level error messages (used in logger calls, not sent to the frontend)
_OIDC_ERR_MISSING_CODE = "Missing authorization code"
_OIDC_ERR_STATE_EXPIRED = "Login session expired. Please try again."
_OIDC_ERR_PROVIDER_UNAVAILABLE = "Identity provider not available"
_OIDC_ERR_DISCOVERY_FAILED = "Failed to connect to identity provider"
_OIDC_ERR_AUTH_FAILED = "Authentication failed. Please try again."
_OIDC_ERR_USER_FAILED = "Unable to sign in. Contact your administrator."
_OIDC_ERR_TLS_VERIFY_FAILED = (
    "TLS certificate verification failed. "
    'If the provider uses a self-signed certificate, enable "Skip TLS certificate verification" '
    "in the identity provider settings."
)
_OIDC_ERR_NO_GROUP_MATCH = (
    "Access denied. Your identity provider groups do not match any configured group mappings. "
    "Contact your administrator."
)


@router.get(
    "/oidc/callback",
    operation_id="oidc_callback",
    dependencies=[NO_PERMISSION],
    summary="OIDC callback",
    description=(
        "Handles the OIDC callback after the user authenticates at the identity provider.\n"
        "Exchanges the authorization code for tokens, validates the ID token,\n"
        "creates or maps a local user, and establishes a session.\n"
    ),
    responses={
        302: {"description": "Redirect to frontend after successful login"},
        401: {"description": "Authentication failed"},
    },
    response_model=None,
)
@audit(EventCategory.SECURITY_EVENT)
async def oidc_callback(
    state: Annotated[str, Query(description="OIDC state parameter for CSRF protection")],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    code: Annotated[str | None, Query(description="Authorization code from identity provider")] = None,
    error: Annotated[str | None, Query(description="Error code from identity provider")] = None,
    error_description: Annotated[
        str | None, Query(description="Human-readable error description from identity provider")
    ] = None,
) -> RedirectResponse:
    """Handle OIDC callback. Exchanges code for tokens, creates session."""
    try:
        (
            user,
            provider,
            state_data,
            identity,
            raw_merged_claims,
            id_token_raw,
            is_first_login,
        ) = await _process_oidc_callback(
            state=state,
            db=db,
            code=code,
            error=error,
            error_description=error_description,
        )
        if user is not None:
            AuditEventDispatcher.dispatch(
                OIDCFlowEvent(
                    provider_id=provider.id, stage=OIDCStage.CALLBACK, user_id=user.id, username=user.username
                )
            )
    except OIDCCallbackError as e:
        AuditEventDispatcher.dispatch(
            OIDCFlowEvent(provider_id=None, stage=OIDCStage.CALLBACK, error_type=type(e).__name__)
        )
        return _build_callback_error_redirect(e)
    except SessionStoreUnavailableError:
        raise
    except Exception:
        logger.exception(
            "Unexpected error during OIDC callback",
            state=state[:8] + "..." if state else None,
            code_present=code is not None,
            error=error,
        )
        base_url = _get_frontend_base_url(None)
        return RedirectResponse(url=f"{base_url}?auth_error={quote(OIDCErrorCode.AUTH_FAILED)}", status_code=302)

    flow_type = state_data.get("flow_type")

    # Handle test-signin flow — return raw claims to the popup window
    if flow_type == "test_signin":
        return _build_test_signin_response(raw_merged_claims, state_data.get("origin"))

    # For link flow: if a local user was converted to federated, identity is non-None
    # and we must create a new session (the old password session was revoked).
    # Otherwise, just redirect back — the existing session is still valid.
    if flow_type == "link":
        return await _build_link_redirect(user, provider, identity, state_data, request, db, id_token_raw)

    # Login flow: user and identity are guaranteed non-None here
    if user is None or identity is None:  # pragma: no cover - defensive guard for type narrowing
        base_url = _get_frontend_base_url(None)
        return RedirectResponse(url=f"{base_url}?auth_error={quote(OIDCErrorCode.AUTH_FAILED)}", status_code=302)

    return await _build_login_session_redirect(
        user, provider, identity, state_data, request, db, id_token_raw, is_first_login=is_first_login
    )


def _build_authorize_error_redirect(
    origin: str | None,
    redirect_to: str | None,
    flow: str | None,
    error_code: str,
) -> RedirectResponse:
    """Build error redirect for OIDC authorize failures.

    For link flows, redirects back to the originating page with link_error
    so the UI can display the error inline instead of dumping the user
    on the base URL.
    """
    if flow == "link" and redirect_to:
        safe_redirect = _safe_redirect_url(redirect_to, origin=origin)
        return RedirectResponse(url=f"{safe_redirect}?link_error={quote(error_code)}", status_code=302)
    base_url = _get_frontend_base_url(origin)
    return RedirectResponse(url=f"{base_url}?auth_error={quote(error_code)}", status_code=302)


def _build_callback_error_redirect(e: "OIDCCallbackError") -> RedirectResponse:
    """Build error redirect for OIDC callback failures."""
    if e.redirect_to:
        safe_redirect = _safe_redirect_url(e.redirect_to, origin=e.origin)
        return RedirectResponse(url=f"{safe_redirect}?link_error={quote(e.error_code)}", status_code=302)
    base_url = _get_frontend_base_url(e.origin)
    return RedirectResponse(url=f"{base_url}?auth_error={quote(e.error_code)}", status_code=302)


async def _build_link_redirect(
    user: User | None,
    provider: IdentityProvider,
    identity: UserIdentity | None,
    state_data: dict[str, str],
    request: Request,
    db: AsyncSession,
    id_token_raw: str,
) -> RedirectResponse:
    """Build redirect after successful identity link.

    When *identity* is non-None a local user was converted to federated
    and a new OIDC session is created (the old password session was revoked).
    """
    if identity is not None and user is not None:
        return await _build_login_session_redirect(
            user, provider, identity, state_data, request, db, id_token_raw, is_first_login=False
        )
    stored_origin = state_data.get("origin")
    redirect_to = _safe_redirect_url(state_data.get("redirect_to"), origin=stored_origin)
    logger.info("OIDC identity link successful", user_id=str(user.id) if user else "unknown", provider=provider.name)
    return RedirectResponse(url=redirect_to, status_code=302)


async def _build_login_session_redirect(
    user: User,
    provider: IdentityProvider,
    identity: UserIdentity,
    state_data: dict[str, str],
    request: Request,
    db: AsyncSession,
    id_token_raw: str,
    *,
    is_first_login: bool,
) -> RedirectResponse:
    """Create session and build redirect after successful OIDC login."""
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    token_service = _get_token_service()
    refresh_token_str, jti, _exp = token_service.create_refresh_token(user.id)

    # Encrypt ID token for RP-initiated logout if enabled for this provider
    encrypted_id_token: str | None = None
    rp_logout_enabled = (
        isinstance(provider.configuration, OIDCConfiguration) and provider.configuration.enable_rp_initiated_logout
    )
    if rp_logout_enabled:
        settings = get_settings()
        key = key_from_string(get_encryption_key().get_secret_value())
        encryptor = SecretEncryptor(key)
        encrypted_id_token = encryptor.encrypt_field(id_token_raw, "session", "id_token_hint")

    try:
        store = create_session_store(db)
        await store.create(
            jti=jti,
            user_id=user.id,
            device=user_agent,
            ip_address=client_host,
            amr=[AMR.FEDERATED],
            idp=provider.name,
            idp_id=str(provider.id),
            identity_id=str(identity.id),
            issuer=identity.issuer,
            subject=identity.subject,
            id_token_hint=encrypted_id_token,
            rp_logout_enabled=rp_logout_enabled,
        )
    except SQLAlchemyError as exc:
        AuditEventDispatcher.dispatch(
            SessionLifecycleEvent(
                action=SessionAction.CREATE,
                user_id=user.id,
                username=user.username,
                jti=jti,
                idp=provider.name,
                error_type=type(exc).__name__,
            )
        )
        AuditEventDispatcher.dispatch(
            LoginAttemptEvent(username=user.username, method=LoginMethod.OIDC, error_type=type(exc).__name__)
        )
        logger.exception("Session store failed during OIDC callback", error=str(exc))
        await db.rollback()
        raise SessionStoreUnavailableError from exc
    AuditEventDispatcher.dispatch(
        SessionLifecycleEvent(
            action=SessionAction.CREATE, user_id=user.id, username=user.username, jti=jti, idp=provider.name
        )
    )

    # OIDC callback has no JWT yet — attribute last_login CRUD to the user (AAP-83651).
    with actor_context(actor=user):
        user.update_last_login()
        db.add(user)
        await db.commit()

    stored_origin = _revalidate_origin(state_data.get("origin"))
    redirect_to = _safe_redirect_url(state_data.get("redirect_to"), origin=stored_origin)

    csrf_seed = generate_csrf_seed()

    response = RedirectResponse(url=redirect_to, status_code=302)
    settings = get_settings()
    cookie_max_age = settings.jwt_refresh_token_lifetime_hours * 3600
    set_refresh_cookie(response, refresh_token_str, max_age=cookie_max_age)
    set_csrf_cookie(response, csrf_seed, max_age=cookie_max_age)

    AuditEventDispatcher.dispatch(
        UserLoginEvent(
            user_id=user.id,
            username=user.username,
            amr=[AMR.FEDERATED],
            idp=provider.name,
            is_first_login=is_first_login,
        )
    )
    logger.info("OIDC login successful", user_id=str(user.id), provider=provider.name)
    AuditEventDispatcher.dispatch(LoginAttemptEvent(username=user.username, method=LoginMethod.OIDC, user_id=user.id))
    return response


def _extract_referer_origin(request: Request) -> str | None:
    """Extract the origin from the Referer header, validated against CORS allowed origins.

    Only returns the origin if it matches one of the configured CORS_ALLOW_ORIGINS.
    This prevents storing an untrusted origin that could be used for open redirects.
    """
    referer = request.headers.get("referer")
    if not referer:
        return None

    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return None

    origin = f"{parsed.scheme}://{parsed.netloc}"

    settings = get_settings()
    for allowed in settings.cors_allow_origins:
        if allowed == origin:
            return allowed

    logger.debug("Referer origin not in CORS allowed origins", origin=origin)
    return None


def _revalidate_origin(origin: str | None) -> str | None:
    """Re-validate a stored origin against the current CORS allowed origins.

    The origin is initially validated during the authorize step, but CORS
    configuration may change before the callback completes. This ensures
    the origin is still trusted before using it for redirection.
    """
    if not origin:
        return None

    settings = get_settings()
    for allowed in settings.cors_allow_origins:
        if allowed == origin:
            return allowed

    logger.warning("Stored OIDC origin no longer in CORS allowed origins, discarding", origin=origin)
    return None


def _get_frontend_base_url(origin: str | None = None) -> str:
    """Return the trusted frontend base URL.

    Fallback chain:
    1. Stored origin from authorize step (captured from Referer, validated against CORS origins)
    2. jwt_issuer (server origin — last resort)
    """
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return origin
        logger.warning("Rejected frontend base URL with invalid scheme", origin=origin)

    return get_settings().jwt_issuer


def _safe_redirect_url(url: str | None, *, origin: str | None = None) -> str:
    """Validate a redirect URL to prevent open-redirect attacks.

    Only allows:
    - Relative paths — resolved against the trusted frontend origin
    - Absolute URLs whose origin is in CORS_ALLOW_ORIGINS

    Falls back to the frontend base URL if the input is unsafe or missing.
    """
    base_url = _get_frontend_base_url(origin)

    if not url:
        return base_url

    parsed = urlparse(url)

    # Allow relative paths (no scheme/host) — resolve against frontend origin
    if not parsed.scheme and not parsed.netloc:
        # Reject protocol-relative URLs like "//evil.com"
        if url.startswith("//"):
            logger.warning("Rejected protocol-relative redirect URL", url=url)
            return base_url
        return f"{base_url}{url}"

    # Allow absolute URLs whose origin is in CORS_ALLOW_ORIGINS
    candidate_origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed_origins = get_settings().cors_allow_origins
    if "*" in allowed_origins:
        logger.warning("Wildcard in CORS_ALLOW_ORIGINS, rejecting absolute redirect for safety", url=url)
        return base_url
    if candidate_origin in allowed_origins:
        return url

    logger.warning("Rejected redirect URL not in CORS origins", url=url, candidate_origin=candidate_origin)
    return base_url


async def _process_oidc_callback(
    *,
    state: str,
    db: AsyncSession,
    code: str | None,
    error: str | None,
    error_description: str | None,
) -> tuple[User | None, IdentityProvider, dict[str, str], UserIdentity | None, dict[str, Any], str, bool]:
    """Process the OIDC callback flow.

    Returns:
        Tuple of (user, provider, state_data, identity, raw_merged_claims, id_token_raw, is_first_login) on success.
        user is None for test_signin flow. identity is None for link/test_signin flows.

    """
    oidc_service = OIDCService()
    state_data = oidc_service.retrieve_oidc_state(state)
    if state_data is None:
        logger.warning("OIDC callback with invalid or expired state")
        raise OIDCCallbackError(_OIDC_ERR_STATE_EXPIRED, error_code=OIDCErrorCode.STATE_EXPIRED)

    origin = _revalidate_origin(state_data.get("origin"))

    if error:
        logger.warning("OIDC provider returned error", error=error, description=error_description)
        raise OIDCCallbackError(_OIDC_ERR_AUTH_FAILED, error_code=OIDCErrorCode.AUTH_FAILED, origin=origin)

    if not code:
        logger.warning("OIDC callback missing authorization code")
        raise OIDCCallbackError(_OIDC_ERR_MISSING_CODE, error_code=OIDCErrorCode.MISSING_CODE, origin=origin)

    try:
        provider = await _load_enabled_provider(db, state_data["provider_id"])
    except OIDCError as e:
        raise OIDCCallbackError(
            _OIDC_ERR_PROVIDER_UNAVAILABLE, error_code=OIDCErrorCode.PROVIDER_UNAVAILABLE, origin=origin
        ) from e

    config = await _load_provider_config(db, provider)

    try:
        discovery = await _get_oidc_endpoints(oidc_service, config)
    except OIDCError as e:
        logger.exception("OIDC endpoint resolution failed during callback")
        msg = _OIDC_ERR_TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else _OIDC_ERR_DISCOVERY_FAILED
        code_ = OIDCErrorCode.TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else OIDCErrorCode.DISCOVERY_FAILED
        raise OIDCCallbackError(msg, error_code=code_, origin=origin) from e

    redirect_uri = str(config.redirect_uri)

    try:
        user_claims, raw_merged_claims, id_token_raw = await _exchange_and_validate_tokens(
            oidc_service,
            discovery,
            config,
            redirect_uri,
            code,
            state_data["code_verifier"],
            state_data["nonce"],
        )
    except OIDCError as e:
        logger.warning("OIDC token exchange/validation failed", error=str(e), provider=provider.name)
        msg = _OIDC_ERR_TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else _OIDC_ERR_AUTH_FAILED
        code_ = OIDCErrorCode.TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else OIDCErrorCode.AUTH_FAILED
        raise OIDCCallbackError(msg, error_code=code_, origin=origin) from e
    except Exception as e:
        logger.exception("Unexpected error during OIDC token exchange", provider=provider.name)
        msg = _OIDC_ERR_TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else _OIDC_ERR_AUTH_FAILED
        code_ = OIDCErrorCode.TLS_VERIFY_FAILED if _is_ssl_verification_error(e) else OIDCErrorCode.AUTH_FAILED
        raise OIDCCallbackError(msg, error_code=code_, origin=origin) from e

    # Handle test-signin flow — return raw claims to frontend, no session created
    if state_data.get("flow_type") == "test_signin":
        return None, provider, state_data, None, raw_merged_claims, id_token_raw, False

    # Handle self-service link flow — create identity for authenticated user
    if state_data.get("flow_type") == "link":
        user, link_identity = await _process_link_callback(db, state_data, user_claims, provider, origin)
        return user, provider, state_data, link_identity, raw_merged_claims, id_token_raw, False

    user, identity, is_first_login = await _resolve_and_login_user(db, user_claims, raw_merged_claims, provider, origin)
    return user, provider, state_data, identity, raw_merged_claims, id_token_raw, is_first_login


async def _resolve_and_login_user(
    db: AsyncSession,
    user_claims: dict[str, str | None],
    raw_merged_claims: dict[str, Any],
    provider: IdentityProvider,
    origin: str | None,
) -> tuple[User, UserIdentity, bool]:
    """Resolve or create a user from OIDC claims, sync groups, and update last login.

    Returns:
        Tuple of (User, UserIdentity, is_first_login) for session tracking

    """
    # Cache provider attributes before any DB rollback can expire the ORM object
    provider_name = provider.name
    provider_config = provider.configuration if isinstance(provider.configuration, OIDCConfiguration) else None

    try:
        user, identity = await _resolve_oidc_user(db, user_claims, provider)
    except OIDCError as e:
        logger.warning("OIDC user resolution failed", error=str(e), provider=provider_name)
        error_code = e.error_code or OIDCErrorCode.USER_FAILED
        raise OIDCCallbackError(str(e), error_code=error_code, origin=origin) from e
    except Exception as e:
        logger.exception("Unexpected error during OIDC user resolution", provider=provider_name)
        raise OIDCCallbackError(_OIDC_ERR_USER_FAILED, error_code=OIDCErrorCode.USER_FAILED, origin=origin) from e

    # Sync IdP group memberships before committing
    if provider_config is not None:
        groups_matched = await sync_idp_groups(db, user, identity, raw_merged_claims, provider_config)

        if not groups_matched:
            # Flush so the sync changes are visible to the membership check below
            await db.flush()
            # No groups resolved from this provider (no mappings matched
            # or extraction failed) — check if the user has any group
            # memberships from other sources (manually assigned),
            # excluding the authenticated group which all users have.
            other_groups = await db.exec(
                select(user_groups.c.group_id)
                .join(Group, Group.id == user_groups.c.group_id)  # type: ignore[arg-type]
                .where(
                    user_groups.c.user_id == user.id,
                    Group.name != AUTHENTICATED_GROUP_NAME,
                    Group.deleted_at.is_(None),  # type: ignore[union-attr]
                )
                .limit(1)
            )
            if other_groups.first() is None:
                logger.error(
                    "Login denied: no group mappings matched and user has no other groups",
                    user_id=str(user.id),
                    provider=provider_name,
                )
                await db.rollback()
                raise OIDCCallbackError(
                    _OIDC_ERR_NO_GROUP_MATCH, error_code=OIDCErrorCode.NO_GROUP_MATCH, origin=origin
                )

    is_first_login = user.last_login is None
    return (user, identity, is_first_login)


async def _process_link_callback(
    db: AsyncSession,
    state_data: dict[str, str],
    user_claims: dict[str, str | None],
    provider: IdentityProvider,
    origin: str | None,
) -> tuple[User, UserIdentity | None]:
    """Process the OIDC callback for identity linking. Wraps _handle_link_flow with error handling.

    Returns:
        Tuple of (user, identity). Identity is non-None when a local user was
        converted to federated — the caller must create a new session.

    """
    link_redirect = state_data.get("redirect_to")
    try:
        return await _handle_link_flow(db, state_data, user_claims, provider)
    except OIDCError as e:
        logger.warning("OIDC link flow failed", error=str(e), provider=provider.name)
        raise OIDCCallbackError(
            str(e), error_code=e.error_code or OIDCErrorCode.LINK_FAILED, origin=origin, redirect_to=link_redirect
        ) from e
    except Exception as e:
        logger.exception("Unexpected error during OIDC link flow", provider=provider.name)
        msg = "Failed to link identity"
        raise OIDCCallbackError(
            msg, error_code=OIDCErrorCode.LINK_FAILED, origin=origin, redirect_to=link_redirect
        ) from e


async def _verify_link_session(db: AsyncSession, session_jti: str | None, user_id_str: str) -> None:
    """Re-verify the session that initiated the link flow is still active and owned by the user."""
    if not session_jti:
        return
    store = create_session_store(db)
    session = await store.get(session_jti)
    if session is None:
        msg = "Session expired. Please log in again."
        raise OIDCError(msg)
    if session.user_id != user_id_str:
        logger.warning(
            "Link flow session user mismatch",
            session_user_id=session.user_id,
            state_user_id=user_id_str,
        )
        msg = "Session does not match. Please log in again."
        raise OIDCError(msg)


async def _handle_link_flow(
    db: AsyncSession,
    state_data: dict[str, str],
    user_claims: dict[str, str | None],
    provider: IdentityProvider,
) -> tuple[User, UserIdentity | None]:
    """Handle self-service identity linking for an authenticated user.

    Returns:
        Tuple of (user, identity). Identity is non-None when a local user was
        converted to federated, signalling the caller to create a new session.

    """
    user_id_str = state_data.get("user_id")
    if not user_id_str:
        msg = "Invalid link flow state"
        raise OIDCError(msg)

    user_id = UUID(user_id_str)

    await _verify_link_session(db, state_data.get("session_jti"), user_id_str)

    user = await _load_active_user(db, user_id)

    if user.is_builtin:
        msg = "Cannot link federated identity to a built-in user account"
        raise OIDCError(msg)

    sub = _validate_sub_claim(user_claims)

    issuer = str(provider.configuration.issuer_url)
    identity_service = UserIdentityService(db)
    was_local = user.auth_type == AuthType.LOCAL

    # Check if this (issuer, sub) is already linked to any user
    existing = await identity_service.find_by_issuer_and_subject(issuer, sub)
    if existing:
        # If linked to a deleted user, clean up the stale identity and proceed
        linked_user = await _find_non_deleted_user(db, existing.user_id)
        if linked_user is None:
            logger.info(
                "Removing stale identity for deleted user during link flow",
                identity_id=str(existing.id),
                deleted_user_id=str(existing.user_id),
            )
            await identity_service.delete_identity(existing.id, force=True)
        elif linked_user.id == user_id:
            msg = "This identity is already linked to your account"
            raise OIDCError(msg, error_code=OIDCErrorCode.IDENTITY_ALREADY_LINKED)
        else:
            msg = "This identity is already linked to another account"
            raise OIDCError(msg, error_code=OIDCErrorCode.IDENTITY_ALREADY_LINKED)

    try:
        identity = await identity_service.create_identity(
            user_id=user.id,
            identity_provider_id=provider.id,
            issuer=issuer,
            subject=sub,
        )
        identity.last_used_at = datetime.now(UTC)
        db.add(identity)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        # Race: another request linked this identity between our check and insert
        existing = await identity_service.find_by_issuer_and_subject(issuer, sub)
        if existing and existing.user_id == user.id:
            # Same user won the race — treat as success
            return await _load_active_user(db, user.id), None
        msg = "This identity is already linked to another account"
        raise OIDCError(msg, error_code=OIDCErrorCode.IDENTITY_ALREADY_LINKED) from e
    except DataError as e:
        await db.rollback()
        msg = "Unable to link identity. Contact your administrator."
        raise OIDCError(msg) from e

    await db.refresh(user)
    return user, identity if was_local else None


def _build_test_signin_response(
    raw_merged_claims: dict[str, Any],
    origin: str | None,
) -> RedirectResponse:
    """Redirect the popup to the frontend origin with claims in a URL fragment.

    The callback lands on the backend origin (redirect_uri), so we can't use
    localStorage or BroadcastChannel (different origin from the frontend).
    Instead, redirect to the frontend origin with base64-encoded claims in the
    hash fragment.  The frontend reads the hash, writes to localStorage on its
    own origin, and closes the popup.
    """
    claims_json = json.dumps(raw_merged_claims, default=str)
    claims_b64 = base64.urlsafe_b64encode(claims_json.encode()).decode()
    base_url = _get_frontend_base_url(origin)
    redirect_url = f"{base_url}/auth/test-signin-callback#{claims_b64}"
    return RedirectResponse(url=redirect_url, status_code=302)
