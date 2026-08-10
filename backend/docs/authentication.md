# Authentication

This document describes how authentication works in Syntara. It is intended for developers working on the project and is updated as the auth system evolves.

## Overview

Syntara supports two authentication methods for human users:

- **Local authentication** — username/password with JWT tokens
- **Federated authentication** — OIDC (OpenID Connect) via external identity providers (Azure AD, Google, Okta, AAP, etc.)

Both methods produce the same JWT access/refresh token pair. Passwords are hashed with Argon2id.

For machine-to-machine authentication (OAuth 2.0 client credentials grant), see [Service Accounts](service-accounts.md).

## Token Lifecycle

### Login (`POST /api/v1/auth/login`)

1. Client sends `{ "username": "...", "password": "..." }`.
2. The username is normalized to lowercase before lookup.
3. Server verifies credentials against the `users` table (`password_hash` column, Argon2id).
4. On success the server returns an access token in the response body and sets the `ao_refresh_token` HttpOnly cookie.

### Refresh (`POST /api/v1/auth/refresh`)

1. The refresh token is read automatically from the `ao_refresh_token` cookie.
2. The server validates the token signature and checks that the session exists in PostgreSQL (a single JOIN query fetches the session and `token_version` together).
3. A new access token is issued with fresh claims from the database — including current group memberships and the latest `token_version` from the users table. The `amr` and `idp` values are preserved from the session metadata (set during login).
4. The refresh token itself is **not rotated** — this is intentional. The fixed expiration acts as a hard session boundary, forcing re-authentication with the identity provider so that group memberships are refreshed on a predictable cadence.

### Logout (`POST /api/v1/auth/logout`)

1. The refresh token session is soft-revoked in PostgreSQL (`revoked_at` is set).
2. The user's `token_version` is incremented, invalidating all outstanding access tokens.
3. The `ao_refresh_token` cookie is cleared.
4. The `StaleTokenMiddleware` rejects subsequent requests using the old access token with `401 TOKEN_STALE` (within ~5 seconds, governed by the middleware's TTL cache). Since the refresh session is also revoked, the client cannot refresh and must re-authenticate.
5. If the session was authenticated via an OIDC provider with RP-initiated logout enabled, the response includes a `redirect_url` the frontend should navigate to (`window.location.href`) to terminate the upstream IdP session.

The logout endpoint always returns JSON (never a 302 redirect). The response includes:

| Field | Description |
|---|---|
| `detail` | `"Successfully logged out"` |
| `redirect_url` | *(optional)* IdP end-session URL for RP-initiated logout. Frontend should navigate to this URL. |
| `auth_error` | *(optional)* Warning when RP-initiated logout is enabled but the IdP's end-session endpoint could not be resolved. |

An optional `post_logout_redirect_uri` query parameter specifies where the IdP should redirect after logout. It is validated against CORS allowed origins (same rules as the login flow). Falls back to the global `APP_OIDC_POST_LOGOUT_REDIRECT_URI` setting.

#### RP-Initiated Logout (OIDC)

When `enable_rp_initiated_logout` is set to `true` on an OIDC provider's configuration, logging out of Nexus also terminates the user's session at the identity provider (per [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)).

**How it works:**

1. During OIDC login, the ID token is encrypted (AES-256-GCM via `APP_SECRET_ENCRYPTION_KEY`) and stored in the session as `id_token_hint`.
2. On logout, the backend resolves the IdP's `end_session_endpoint` — first from the provider's static configuration, falling back to OIDC discovery (`.well-known/openid-configuration`).
3. The backend builds a logout URL with `id_token_hint` (decrypted) and `post_logout_redirect_uri` parameters.
4. The logout JSON response includes `redirect_url` — the frontend navigates to this URL to complete the IdP logout.

**Failure handling:** If the `end_session_endpoint` cannot be resolved (static config missing and discovery fails), the response includes `auth_error` instead of `redirect_url`. The user is logged out of Nexus but remains logged in at the IdP. The frontend should display the warning.

**Configuration:** Set `enable_rp_initiated_logout: true` and optionally `end_session_endpoint` in the provider's OIDC configuration. If `end_session_endpoint` is not set, it is discovered automatically via the OIDC well-known endpoint.

## CSRF Protection

Cookie-authenticated endpoints (`POST /auth/refresh`, `POST /auth/logout`) are protected against Cross-Site Request Forgery using the **Synchronizer Token** pattern with HMAC derivation.

### How it works

1. **Login / OIDC callback** — the server generates a cryptographically random seed, stores it in the `ao_csrf_token` `HttpOnly` cookie, and derives a form token via `HMAC-SHA256(server_secret, seed)`.
2. **SPA obtains the form token** — after login or OIDC redirect, the SPA calls `POST /api/v1/auth/csrf_token`. The server reads the seed from the cookie, recomputes the HMAC, and returns the form token in the response body. The SPA stores it in memory.
3. **Subsequent requests** — the SPA sends the form token in the `X-CSRF-Token` header on state-changing requests (refresh, logout).
4. **Validation** — the server reads the seed from the `ao_csrf_token` cookie, recomputes the expected form token, and compares it to the header value using `hmac.compare_digest` (timing-safe).

### Why HMAC derivation?

The cookie seed alone is insufficient to forge the form token — the server-side `APP_SECRET_ENCRYPTION_KEY` is required as the HMAC key. Even if an attacker can read the cookie (e.g., via a subdomain XSS), they cannot produce a valid form token without the server secret.

### Cookie details

| Property | Value |
|---|---|
| Name | `ao_csrf_token` |
| Path | `/api/v1/auth` |
| HttpOnly | `true` |
| Secure | Derived from `APP_SERVER_SCHEME` (same as refresh cookie) |
| SameSite | `Lax` |
| Max-Age | Same as the refresh token cookie (`APP_JWT_REFRESH_TOKEN_LIFETIME_HOURS × 3600`) |
| Domain | `APP_COOKIE_DOMAIN` |

### Bearer token exemption

Requests authenticated via `Authorization: Bearer <token>` (i.e., non-cookie auth) are exempt from CSRF validation. CSRF attacks exploit the browser's automatic cookie attachment — bearer tokens are not sent automatically, so they are not vulnerable.

### Current User (`GET /api/v1/auth/me`)

Returns the authenticated user's information from the access token claims (no database round-trip). Includes `id`, `username`, `email`, `role`, `groups`, and `rp_logout_enabled` (whether the user's current session supports RP-initiated logout).

## Token Details

| Property | Access Token | Refresh Token |
|---|---|---|
| Algorithm | ES256 | ES256 |
| Default lifetime | 15 minutes | 8 hours |
| Transport | `Authorization: Bearer <token>` | `ao_refresh_token` HttpOnly cookie |
| Contains | `sub`, `iss`, `iat`, `exp`, `name`, `preferred_username`, `email`, `role`, `groups`, `token_ver`, `amr`, `idp` | `sub`, `iss`, `iat`, `exp`, `jti` |
| Server-side state | None (stateless) | Session stored in PostgreSQL `refresh_sessions` table (keyed by `jti`) |

## Session Storage

Refresh token sessions are stored in the PostgreSQL `refresh_sessions` table, keyed by `jti` (JWT ID). Each session records:

- `user_id` — UUID of the authenticated user (FK to `users.id` with CASCADE)
- `issued_at` — when the session was created
- `expires_at` — when the session expires
- `revoked_at` — soft-revocation timestamp (NULL = active, set on revoke)
- `device` — User-Agent string
- `ip_address` — client IP
- `amr` — authentication method references (e.g., `["pwd"]` for local, `["fed"]` for OIDC)
- `idp` — identity provider name (e.g., `"local"`, `"Azure"`)
- `idp_id` — identity provider UUID for indexed bulk revocation
- `identity_id` — UserIdentity UUID for indexed bulk revocation
- `issuer` — OIDC issuer URL for federated sessions
- `subject` — OIDC subject claim for federated sessions
- `id_token_hint` — encrypted ID token for RP-initiated logout (only stored when `enable_rp_initiated_logout` is enabled on the provider)

Expired sessions are physically deleted by an hourly background cleanup worker (batched in groups of 1000 to avoid long-running transactions).

### Database Indexes

Partial indexes (`WHERE revoked_at IS NULL`) keep index size small and lookups fast:

1. **`ix_refresh_sessions_user_id`** — for `revoke_all_for_user` and `list_user_sessions`. Enables O(1) bulk revocation via indexed UPDATE.

2. **`ix_refresh_sessions_idp_id`** — for bulk revocation when a provider is deleted. Enables O(m) revocation.

3. **`ix_refresh_sessions_identity_id`** — for bulk revocation when an identity is moved or deleted. Enables O(m) revocation.

4. **`ix_refresh_sessions_expires_at`** — for the cleanup worker to efficiently find expired sessions.

### Session Revocation

Sessions are soft-revoked (`revoked_at` is set) when:

| Event | Scope | Method |
|-------|-------|--------|
| **Password change** | All sessions for user | User's password is updated via `PATCH /users/{id}` |
| **Account disabled** | All sessions for user | User's `is_enabled` is set to `false` via `PATCH /users/{id}` |
| **Account deletion** | All sessions for user | User is soft-deleted via `DELETE /users/{id}` |
| **Logout** | Single session | User logs out via `POST /auth/logout` (revokes current session only) |
| **Provider deletion** | All sessions for provider | Identity provider is deleted — uses `ix_refresh_sessions_idp_id` index |
| **Identity re-association** | All sessions for both source and target users | Identity moved to different user via `POST /auth/users/{user_id}/identities`. Token version incremented for both users |
| **Identity deletion** | All sessions for user | Identity detached via `DELETE /auth/users/{user_id}/identities/{identity_id}`. Token version incremented |

Stateless access tokens cannot be individually revoked. However, the `StaleTokenMiddleware` rejects requests from disabled users within ~5 seconds of the disable action (via the same TTL-cached DB query used for stale token detection). See [Disabled User Enforcement](#disabled-user-enforcement).

### Global Token Revocation

In an emergency (e.g., suspected key compromise, bulk account takeover, or compliance-mandated session termination), an administrator can invalidate **all** tokens issued before a given point in time using either the admin CLI or the REST API.

#### CLI Usage

```bash
# Interactive — prompts for confirmation
uv run python -m syntara.admin revoke-all-sessions

# Non-interactive (CI/scripts)
uv run python -m syntara.admin revoke-all-sessions --yes
```

#### API Usage

```
POST /api/v1/admin/revocation
Authorization: Bearer <admin-token>
```

Returns `200` with the revocation timestamp. Requires the `admin` role.

To read the current revocation timestamp:

```
GET /api/v1/admin/revocation
Authorization: Bearer <token>
```

Returns `200` with `revoked_before` and `updated_at` (both `null` if no revocation has been performed). Accessible to `admin` and `auditor` roles.

#### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--yes` | `false` | Skip the confirmation prompt |

#### What happens when revocation runs

1. The `revoked_before` column in the `global_revocation_timestamp` table is updated to the current UTC time. If no row exists yet, the singleton row is inserted.
2. An audit event (`global_revocation`) is emitted with the actor name, source (`cli` or `api`), and timestamp.

#### How enforcement works

Once the timestamp is set, every authenticated request is checked:

- **Access tokens** (`get_current_user` dependency) — if the token's `iat` is before `revocation_ts + cache_TTL`, the request is rejected with `401 TOKEN_GLOBALLY_REVOKED`. The user must re-authenticate.
- **Refresh tokens** (`POST /auth/refresh`) — same check. The refresh cookie is cleared and the request is rejected with `401 TOKEN_GLOBALLY_REVOKED`. The user must log in again.

The comparison uses `iat < revocation_ts + cache_TTL` rather than `iat < revocation_ts`. This **TTL-adjusted boundary** compensates for cache staleness across API nodes: even if another node is still serving a stale cached value, tokens issued during that staleness window are rejected once the cache refreshes. The trade-off is that tokens issued in the few seconds *after* a revocation event may also require re-authentication — an acceptable cost for closing the multi-node bypass window.

Tokens issued **after** `revocation_ts + cache_TTL` are unaffected.

#### Performance and caching

The global revocation timestamp is cached in each API worker process for **10 seconds** (in-process `cachetools.TTLCache`). This avoids a database round-trip on every authenticated request while keeping the propagation delay short.

**Eventual consistency model:** After an admin sets the revocation timestamp, enforcement propagates across all API nodes within the cache TTL. During this window, a node with a stale cache may still accept pre-revocation tokens. Once the cache expires, the next request fetches the updated timestamp and enforcement takes effect. The TTL-adjusted comparison ensures that tokens issued during the staleness window are also rejected, closing the multi-node bypass.

**Thundering-herd protection:** On cache miss, an `asyncio.Lock` ensures only one coroutine queries the database; concurrent callers wait for the result. This prevents connection pool flooding under high concurrency.

**Session reuse:** The revocation check piggybacks on the database session the request already holds (via FastAPI's `Depends(get_db)` deduplication). No additional database connections are checked out from the pool.

#### Audit trail

Two audit events are emitted:

| Event | When | Fields |
|-------|------|--------|
| `global_revocation` | Admin triggers revocation (CLI or API) | `actor_username`, `actor_source` (`cli` or `api`), `revocation_timestamp` |
| `global_revocation_reject` | A token is rejected | `user_id`, `username`, `token_type` (`access` or `refresh`), `token_issued_at`, `revocation_timestamp` |

### User Session Revocation

An administrator can revoke all active sessions for a specific user without affecting other users. This is useful for incident response (e.g., compromised account) or administrative actions (e.g., revoking access for a departing employee).

#### CLI Usage

```bash
# Interactive — prompts for confirmation
uv run python -m syntara.admin revoke-user-sessions --username alice

# Non-interactive (CI/scripts)
uv run python -m syntara.admin revoke-user-sessions --username alice --yes
```

#### API Usage

```
POST /api/v1/admin/revocation/users/{username}
Authorization: Bearer <admin-token>
```

Returns `200` with `message` and `sessions_revoked`. Returns `404` if the user does not exist. Requires the `admin` role.

#### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | *(required)* | Username of the user whose sessions should be revoked (case-insensitive) |
| `--yes` | `false` | Skip the confirmation prompt |

#### What happens when revocation runs

1. The user is looked up by username in the database (case-insensitive, non-deleted users only).
2. All refresh token sessions for the user are deleted from the session store via `revoke_all_for_user()`.
3. The user's token version counter is incremented so any remaining access tokens trigger a refresh attempt, which will issue a new token with current claims.
4. An audit event (`session_revocation`) is emitted with the actor name, target username, and number of sessions revoked.

### IdP Session Revocation

An administrator can revoke all active sessions that were authenticated via a specific identity provider. This is useful when an IdP is compromised, misconfigured, or being decommissioned — without needing to delete the provider itself.

#### CLI Usage

```bash
# Interactive — prompts for confirmation
uv run python -m syntara.admin revoke-idp-sessions --idp-name "Corporate Okta"

# Non-interactive (CI/scripts)
uv run python -m syntara.admin revoke-idp-sessions --idp-name "Corporate Okta" --yes
```

#### API Usage

```
POST /api/v1/admin/revocation/identity_providers/{idp_name}
Authorization: Bearer <admin-token>
```

Returns `200` with `message` and `sessions_revoked`. Returns `404` if the identity provider does not exist. Requires the `admin` role.

#### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--idp-name` | *(required)* | Name of the identity provider whose sessions should be revoked |
| `--yes` | `false` | Skip the confirmation prompt |

#### What happens when revocation runs

1. The identity provider is looked up by name in the database (non-deleted providers only).
2. All refresh token sessions authenticated via this provider are deleted from the session store using the `idp_sessions:<provider_id>` secondary index.
3. An audit event (`session_revocation`) is emitted with the actor name, target provider name, and number of sessions revoked.

Users who authenticated via this provider will need to re-authenticate. Sessions from other providers and local password sessions are unaffected.

### Revocation Audit Trail

All revocation operations (CLI and API) emit audit events. The `actor_source` field distinguishes the origin (`cli` or `api`).

| Operation | Event | Fields |
|-----------|-------|--------|
| Revoke all sessions | `global_token_revocation` | `actor_username`, `actor_source`, `revocation_timestamp` |
| Revoke user sessions | `session_revocation` | `actor_username`, `actor_source`, `target_type` (`user`), `target_identifier`, `sessions_revoked` |
| Revoke IdP sessions | `session_revocation` | `actor_username`, `actor_source`, `target_type` (`idp`), `target_identifier`, `sessions_revoked` |

### Account Management (`orchestrator-admin`)

The `orchestrator-admin` CLI provides production account management operations, designed to be run inside the application pod. It is a separate CLI from the developer `python -m syntara.admin` utility.

#### Account Re-enablement

Re-enables a disabled user account. Works for both local and identity provider users.

```bash
# Interactive — prompts for confirmation (defaults to admin user)
orchestrator-admin enable-user

# Specify a different user
orchestrator-admin enable-user --username alice

# Non-interactive (CI/scripts)
orchestrator-admin enable-user --username alice --yes
```

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | `admin` | Username of the account to re-enable (case-insensitive) |
| `--yes` | `false` | Skip the confirmation prompt |

**What happens when the command runs:**

1. The user is looked up by username (case-insensitive, non-deleted users only).
2. If the user is already enabled, the command exits cleanly (idempotent).
3. The user's `is_enabled` flag is set to `true`.
4. All existing sessions are revoked and the token version is incremented (forces fresh login).
5. An audit event (`account_enable`) is emitted.
6. For local users, the output suggests running `orchestrator-admin reset-password` if a password reset is also needed.

#### Password Reset

Resets the password for a local user account. Identity provider users are rejected with a clear error (their credentials are managed by the external identity provider).

```bash
# Interactive — prompts for confirmation, then prompts for new password (no echo)
orchestrator-admin reset-password --username alice

# Non-interactive confirmation (still prompts for password securely)
orchestrator-admin reset-password --username alice --yes

# Non-interactive — read password from stdin (recommended for scripts)
cat /run/secrets/admin-password | orchestrator-admin reset-password --username alice --password-stdin

# Non-interactive — provide password as flag (⚠️ visible in process list and shell history)
orchestrator-admin reset-password --username alice --password 'MySecureP@ss1'
```

| Flag | Default | Description |
|------|---------|-------------|
| `--username` | *(required)* | Username of the account whose password will be reset |
| `--password-stdin` | `false` | Read the new password from stdin (one line). Recommended for scripts and automation. |
| `--password` | *(none)* | New password as a CLI argument. **Insecure** — the value is visible in the process list (`ps`) and may be saved in shell history. Prefer `--password-stdin`. |
| `--yes` | `false` | Skip the confirmation prompt |

> **Security note:** `--password` exposes the password in the process list and shell history. For automation, prefer `--password-stdin` which reads from a pipe or file and leaves no trace in process arguments:
>
> ```bash
> cat /run/secrets/admin-password | orchestrator-admin reset-password --username alice --password-stdin
> ```

When the password is supplied via `--password` or `--password-stdin`, the confirmation prompt is automatically skipped. The two flags are mutually exclusive. If stdin is not a terminal and neither `--password` nor `--password-stdin` is given, the command exits with an error instead of silently consuming input.

**What happens when the command runs:**

1. The password is resolved from `--password` flag, `--password-stdin`, or interactive prompt (with confirmation).
2. If the password came from interactive prompt, the user confirms the operation (unless `--yes`).
3. Password is validated (minimum 14 characters, at least 3 of 4 character classes).
4. The user is looked up by username (case-insensitive, non-deleted users only).
5. Identity provider users are rejected — only local users can have passwords reset.
6. The password is hashed (Argon2id) and stored.
7. All existing sessions are revoked and the token version is incremented.
8. An audit event (`password_reset`) is emitted.

#### Account Management Audit Trail

| Command | Event | Severity | Fields |
|---------|-------|----------|--------|
| `orchestrator-admin enable-user` | `account_enable` | WARNING | `actor_username`, `actor_source`, `target_username`, `sessions_revoked` |
| `orchestrator-admin reset-password` | `password_reset` | CRITICAL | `actor_username`, `actor_source`, `target_username`, `sessions_revoked` |

### Storage Dependencies

Authentication uses **PostgreSQL only** for session storage. Redis is not required for any auth operation. OIDC flow state is encrypted (AES-256-GCM) and encoded in the OAuth2 `state` parameter (no server-side storage required).

| Flow | Storage | Notes |
|------|---------|-------|
| **Login** | PostgreSQL (`refresh_sessions` table) | Session INSERT in same transaction as `last_login` update |
| **Token refresh** | PostgreSQL (JOIN query) | Single query fetches session + `token_version` |
| **Logout** | PostgreSQL | Soft-revoke via `UPDATE SET revoked_at` |
| **OIDC authorize** | None (encrypted state) | State encrypted and encoded in the OAuth2 `state` parameter |
| **OIDC callback** | None (encrypted state) | State decrypted from the `state` parameter |
| **Access token validation** | In-process cache + PostgreSQL | Stateless JWT verified locally; global revocation check via `TTLCache` (10s) reusing the request's DB session |
| **Stale token check** | In-process cache + PostgreSQL | `cachetools.TTLCache` (5s) for `token_version` lookups |

### Token Version (Stale Token Detection) & Disabled User Enforcement

When an admin changes a user's account (group memberships, profile, role, etc.), the user's access token becomes stale — its claims no longer reflect reality. Rather than forcing a logout, Nexus uses a lightweight version counter to trigger a seamless background token refresh.

#### Mechanism

Each user has a `token_version` column on the `users` table. The counter is included in the access token as the `token_ver` claim.

```
Admin changes user's account (groups, profile, etc.) — or user logs out
  -> SQL: UPDATE users SET token_version = token_version + 1 WHERE id = :uid
  -> User's next API request:
       StaleTokenMiddleware compares token's token_ver vs DB version (5s TTLCache)
       Token is stale → 401 TOKEN_STALE response (retryable)
  -> Frontend receives 401 → attempts POST /auth/refresh
       If refresh session is valid → new access token with current token_ver → retry succeeds
       If refresh session is revoked (logout) → refresh fails → redirect to login
  -> UI reflects correct state seamlessly (no forced logout for non-logout scenarios)
```

#### What triggers a version bump

| Endpoint | Action |
|----------|--------|
| `POST /groups/{id}/members` | User added to group |
| `DELETE /groups/{id}/members/{user_id}` | User removed from group |
| `PUT /users/{id}/groups` | User's group memberships replaced |
| `PATCH /users/{id}` | User profile updated (name, email, enabled status, password) |
| `DELETE /users/{id}` | User soft-deleted (next refresh fails → auto-logout) |
| `POST /auth/users/{user_id}/identities` | Identity attached — token version incremented for both source and target users |
| `DELETE /auth/users/{user_id}/identities/{identity_id}` | Identity detached |
| `POST /auth/logout` | User logs out (refresh session also revoked → forced re-authentication) |

#### Backend components

- **`SessionStore.increment_token_version(user_id)`** — called after any admin action that changes a user's account. Uses `UPDATE users SET token_version = token_version + 1 ... RETURNING token_version`. Also invalidates the middleware's in-process TTLCache entry for the user.
- **`SessionStore.get_with_token_version(jti)`** — called during refresh. A single JOIN query fetches the session and the user's `token_version` together, which is embedded in the new access token's `token_ver` claim. During login, `token_version` is read directly from the already-loaded `User` object (zero additional queries).
- **`StaleTokenMiddleware`** — Starlette middleware registered in `main.py`. On every authenticated request, it decodes `sub` and `token_ver` from the token, checks the version via an in-process `cachetools.TTLCache` (5-second TTL, max 4096 entries), and returns `401 TOKEN_STALE` if the token is outdated. The `/auth/logout` and `/auth/refresh` paths are exempted so users can still refresh or log out with a stale token. Cache misses query PostgreSQL directly. Errors are swallowed to avoid blocking requests.

#### Frontend handling

When the middleware returns `401 TOKEN_STALE`, the frontend's `authMiddleware` in `client.tsx` attempts a token refresh via `POST /auth/refresh`. If the refresh succeeds (refresh session still valid), the original request is retried with the new access token — seamless to the user. If the refresh fails (e.g., after logout where the refresh session is revoked), the user is redirected to the login page.

#### Disabled user enforcement

The `StaleTokenMiddleware` also enforces disabled-user rejection. When a user's account is disabled (`is_enabled = false`), the middleware returns `401 ACCOUNT_DISABLED` for all subsequent API requests using that user's access token — without running the request handler.

This closes the window during which a disabled user's stateless JWT would otherwise remain valid (up to 15 minutes). The enforcement uses the same DB query and TTL cache as the stale-token check (zero additional database round-trips). After the cache entry expires (max 5 seconds), the next request fetches the updated `is_enabled` value and enforcement takes effect.

**Error handling**: If the DB query or token decode fails, the middleware fails open (same as the stale-token check). The disabled-user rejection only triggers when `is_enabled = false` is positively confirmed from the database or cache.

## Key Management

JWT signing uses ES256 with keys provided via:

1. **File path** — `APP_JWT_PRIVATE_KEY_PATH` (e.g., `/run/secrets/jwt-primary.pem`)
2. **Base64 env var** — `APP_JWT_PRIVATE_KEY_BASE64` (alternative for environments without file mounts)

For local development, `make secrets-generate` creates both key pairs, an admin password file, and a database encryption key in `.secrets/`.

### Key Rotation

The `KeyManager` and `TokenService` are cached as singletons per process for performance. Rotating a signing key requires two steps:

1. **Deploy the new key alongside the old one** — set `APP_JWT_PRIVATE_KEY_PATH` to the new key and add the old key to `APP_JWT_BACKUP_KEYS`. Backup keys are used for **verification only** (they never sign new tokens), so existing tokens remain valid during the transition.

    ```
    APP_JWT_BACKUP_KEYS='[{"key_id":"nexus-old-key","key_path":"/run/secrets/jwt-old.pem"}]'
    ```

2. **Restart all app processes** — the singleton caches are cleared on restart, causing the new key to be loaded. In Kubernetes this is a rolling restart (`kubectl rollout restart`); with systemd it's a service restart.

Both caches expose `clear_*` functions for programmatic invalidation without a full restart:

```python
from syntara.auth.services.token_service import clear_key_manager_cache
from syntara.auth.dependencies import clear_token_service_cache

# Clear both caches — new keys will be loaded on the next request
clear_key_manager_cache()
clear_token_service_cache()
```

These can be wired to a signal handler or an admin endpoint depending on operational requirements. The simplest production approach is a rolling restart.

### Emergency Key Compromise

Choose a response based on the severity of the compromise:

#### Option A: Immediate revocation (active exploitation suspected)

If the key is being actively exploited, revoke it immediately to stop the attacker from minting new tokens. In-flight tokens signed with the compromised key will fail and users will need to re-authenticate.

1. Generate a new key pair
2. Set `APP_JWT_PRIVATE_KEY_PATH` to the new key — do **not** add the compromised key to `APP_JWT_BACKUP_KEYS`
3. Perform a rolling restart of all app processes
4. All tokens signed with the old key are immediately rejected

#### Option B: Graceful rotation (compromise detected, not actively exploited)

If the compromise is detected but not actively exploited (e.g., a key was accidentally committed to a repo), a graceful rotation avoids disrupting active user sessions.

1. Generate a new key pair
2. Move the compromised key to `APP_JWT_BACKUP_KEYS` (so in-flight tokens can still be verified during the transition)
3. Set `APP_JWT_PRIVATE_KEY_PATH` to the new key
4. Perform a rolling restart of all app processes
5. Once all processes are restarted, remove the compromised key from `APP_JWT_BACKUP_KEYS` and restart again — tokens signed with the old key will be rejected

> **Trade-off**: Option B keeps the compromised key valid for verification during step 4–5. An attacker who exfiltrated the key could mint JWTs during this window. Use Option A if there is any doubt about active exploitation.

## Bootstrap Admin User

On first application startup, an `admin` user is seeded with the password from `APP_ADMIN_PASSWORD_PATH`. This happens in the application lifespan handler via `authz/seed.py`, which reads the password file, hashes it with Argon2id, and creates the user if it doesn't already exist. The admin user is created with `is_builtin=True`, which identifies it as a built-in user with special protection rules.

If the password file is not configured or missing, the application still starts but logs a warning — the admin user will be created without a password (unable to log in locally).

> **Recommended**: Run `make secrets-generate` before first startup to create the password file.

### Built-in Admin Protection

The built-in admin user (identified by `is_builtin=True`) has special protection rules enforced at the API level:

| Action | Who Can Do It | Guard |
|--------|--------------|-------|
| **Modify properties** (username, first_name, last_name, email) | Nobody | `AdminModifyError` (403) |
| **Change password** | Only the admin itself | `AdminModifyError` (403) for non-self |
| **Disable** (`is_enabled=false`) | Only the admin itself, and only when at least one other enabled user exists in the admins group | `AdminModifyError` (403) for non-self; `AdminDisableNoOtherAdminsError` (403) if no other enabled admins |
| **Re-enable** (`is_enabled=true`) | Any admin user | Always allowed |
| **Delete** | Nobody | `AdminDeleteError` (403) |

The disable guard uses `SELECT ... FOR UPDATE` on the admins group row to prevent race conditions where two concurrent requests could both pass the "other admins exist" check and then both disable, leaving zero enabled admins.

Additionally, disabling or deleting *any* user (not just the builtin admin) is blocked if it would leave zero enabled users in the admins group.

### Built-in Group Protection

Built-in groups (`admins`, `authenticated`) are identified by `is_builtin=True` and have the following protections:

| Action | Guard |
|--------|-------|
| **Delete group** | Blocked — `BuiltinGroupDeleteError` (403). Built-in groups cannot be deleted. |
| **Remove builtin user** | Blocked — `LastAdminRemovalError` (403). The built-in admin user cannot be removed from any built-in group (`admins`, `authenticated`). Applies to both `DELETE /groups/{id}/members/{user_id}` and `PUT /users/{id}/groups`. |
| **Remove last enabled admin** | Blocked — `LastAdminRemovalError` (403). Removing *any* user from the `admins` group is blocked if it would leave zero enabled admin members. |

The last-admin-removal guard uses `SELECT ... FOR UPDATE` on the group row to serialize concurrent operations.

### Local Login Setting

The runtime setting `authentication.local_login_enabled` (default: `true`) controls whether non-builtin local users can log in with a password. When disabled, only the built-in admin account can authenticate locally. Identity provider (OIDC) users are not affected.

This is intended to be disabled after identity providers are configured and local password login is no longer needed, reducing the attack surface.

**Login flow with the setting:**

1. User lookup by username
2. If user is non-builtin: check `authentication.local_login_enabled` — reject immediately if `false`
3. Password verification (Argon2id)
4. Account enabled check
5. Token creation

The check runs **before** password verification to avoid unnecessary computation when local login is disabled. Rejected logins return the same generic 401 as any other authentication failure, and the specific reason (`local_login_disabled`) is recorded in the audit log.

**Key behaviors:**

| User type | Setting enabled | Setting disabled |
|-----------|----------------|-----------------|
| Built-in admin | Can log in | Can log in |
| Non-builtin local user | Can log in | Rejected (401) |
| Federated (OIDC) user | Not affected | Not affected |

The setting is managed via **System Administration > Settings > Authentication** in the UI and takes effect within 60 seconds (settings cache TTL).

### Providing a custom admin password

If the `APP_ADMIN_PASSWORD` environment variable is set when `make secrets-generate` (or `make secrets-generate-force`) runs, the script will write that value into `.secrets/admin-password` instead of generating a random one. This lets you control the admin password at deploy time without editing any files.

Set the variable **before** secrets are generated:

```bash
export APP_ADMIN_PASSWORD="my-secure-password"
make secrets-generate-force   # writes the value to .secrets/admin-password
make run-all                  # app startup seeds the admin user with this password
```

If `APP_ADMIN_PASSWORD` is not set, `generate_secrets.sh` creates a random 24-byte base64 password saved to `.secrets/admin-password`:

```bash
cat .secrets/admin-password
```

> **Important**: The admin password is hashed on first creation. If the database already has an `admin` user with a password set, the seed will not overwrite it. To change the password, use the `PATCH /users/{id}` endpoint or reset the database.

## Identity Providers (OIDC)

Nexus supports external identity providers for federated authentication via OpenID Connect.

### Federated Identity Model

Federated identities are tracked in the `user_identities` table, keyed on `(issuer, sub)` — the OIDC issuer URL and subject claim. This replaces the previous email-only matching and enables proper federated identity management.

Key concepts:

- **Identities are keyed on `(issuer, sub)`**, not email. This prevents account confusion when different providers use the same email.
- The `user_identities` table links federated identities to users. Each row represents one OIDC identity.
- **Local users (password-based) have no `user_identities` rows.** The table is exclusively for federated identities.
- **Local and federated users are mutually exclusive.** A user is either local (`auth_type = 'local'`, password-based) or federated (`auth_type = 'federated'`, identity-provider-based), never both. Setting a password on a federated user or linking an identity to a local user returns 409 Conflict. A database CHECK constraint enforces this invariant.
- A federated user can have **multiple federated identities** from different providers.
- Existing OIDC users get their `user_identities` row created automatically on next login.

### Identity Management

Admins can manage federated identities via the API:

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/users/{user_id}/identities` | List federated identities for a user |
| `POST` | `/auth/users/{user_id}/identities` | Attach an identity from another user (`{ identity_id }`) |
| `DELETE` | `/auth/users/{user_id}/identities/{identity_id}` | Detach (hard-delete) an identity |

When attaching an identity from User B to User A, User B's record is preserved even if they have no remaining identities or password. This supports audit trails — an admin can later re-attach an identity or set a password for User B.

Identity management is also available in the UI under each user's "Identities" tab, which supports filtering, sorting, attaching identities from other users, and detaching identities with confirmation.

### OIDC Login Flow

```
User clicks "Log in with Azure"
  -> Frontend redirects to: GET /api/v1/auth/oidc/authorize?provider_id=X
  -> Backend generates auth URL with state/nonce/PKCE encrypted in the OAuth2 state parameter
  -> Backend 302 redirects to provider's authorization endpoint
  -> User authenticates at the provider
  -> Provider redirects to: GET /api/v1/auth/oidc/callback?code=X&state=Y
  -> Backend exchanges code for tokens, validates ID token
  -> Backend looks up UserIdentity by (issuer, sub)
     -> Found + user active: load linked user
     -> Found + user deleted: remove stale identity, proceed as "not found"
     -> Not found: create new user
  -> Backend creates UserIdentity link (if new, with race condition handling)
  -> Backend syncs group memberships from IdP token claims
     -> If no groups resolved and user has no other groups: login denied
  -> Backend creates JWT + refresh token, sets cookie, redirects to frontend
  -> Frontend's bootstrap refresh succeeds -> user is logged in
```

### Public Endpoints

| Method | Path | Description |
|---|---|---|
| `GET /api/v1/auth/providers` | List enabled identity providers for the login page (no auth required) |
| `GET /api/v1/auth/oidc/authorize` | Initiate OIDC login (redirects to provider) |
| `GET /api/v1/auth/oidc/callback` | Handle OIDC callback (exchanges code, creates session) |

### Identity Provider Management

All management endpoints require authentication and are under `/api/v1/identity_providers`:

| Method | Path | Description |
|---|---|---|
| `GET /` | List providers | Paginated list with filtering by name and status |
| `POST /` | Create provider | Register a new identity provider (201) |
| `GET /{provider_id}` | Get provider | Retrieve provider details (secrets excluded) |
| `PATCH /{provider_id}` | Update provider | Partially update (client_secret optional — preserves existing) |
| `DELETE /{provider_id}` | Delete provider | Soft delete a provider (204) |
| `POST /test` | Test connection | Test OIDC discovery without saving |
| `POST /setup-aap-oidc` | Setup AAP provider | Push-button AAP OIDC setup (201) |

### OIDC Configuration

When creating an OIDC identity provider, the top-level fields are:

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Human-readable provider name |
| `enabled` | No | Enable/disable the provider (default: `true`) |
| `configuration` | Yes | OIDC configuration object (see below) |

The `configuration` object includes:

| Field | Required | Description |
|---|---|---|
| `provider_type` | Yes | Must be `"oidc"` |
| `idp_type` | No | Provider type hint (`"aap"`, `"custom"`) for UI pre-configured defaults |
| `issuer_url` | Yes | OIDC issuer URL (e.g., `https://accounts.google.com`) |
| `client_id` | Yes | OAuth 2.0 client ID |
| `client_secret` | Yes (create) | OAuth 2.0 client secret (excluded from responses, optional on patch) |
| `redirect_uri` | Yes | OAuth 2.0 redirect URI (must match provider registration) |
| `auto_discovery` | No | Use `.well-known` auto-discovery (default: `true`) |
| `scopes` | No | Space-separated scopes (default: `"openid profile email"`) |
| `claim_mapping` | No | Maps IdP-specific claim names to Nexus fields (see [Claim Mapping](#claim-mapping)) |
| `group_jmespath_expression` | No | JMESPath expression to extract group values from token claims (see [Group Mapping and Login Enforcement](#group-mapping-and-login-enforcement)) |
| `group_mapping_entries` | No | Maps IdP group values to Nexus groups (see [Group Mapping and Login Enforcement](#group-mapping-and-login-enforcement)) |
| `allow_all_authenticated` | No | Allow all users from this IdP to log in regardless of group mapping results (default: `false`). Users receive the implicit "authenticated" group; group mappings still apply if configured |
| `aap_role_mapping_enabled` | No | Map AAP `aap_system_role` claim (`system_administrator`, `system_auditor`, `normal_user`) to built-in groups (default: `false`). Only effective when `idp_type` is `"aap"`. See [AAP Role Mapping](#aap-role-mapping) |
| `disable_tls_verify` | No | Skip TLS certificate verification when connecting to the provider (default: `false`). See [TLS Certificate Verification](#tls-certificate-verification) |
| `enable_rp_initiated_logout` | No | Enable RP-initiated logout to terminate IdP sessions on Nexus logout (default: `false`) |
| `end_session_endpoint` | No | IdP's end-session endpoint URL. Auto-discovered from `.well-known` if not set |

#### Manual Endpoints (when auto_discovery is disabled)

| Field | Required | Description |
|---|---|---|
| `authorization_endpoint` | Yes | URL where users are redirected to authenticate |
| `token_endpoint` | Yes | URL where authorization codes are exchanged for tokens |
| `jwks_uri` | Yes | URL to fetch public keys for token signature verification |
| `userinfo_endpoint` | No | URL to fetch additional user claims |

### TLS Certificate Verification

By default, Nexus validates the TLS certificate chain when connecting to an OIDC identity provider. This ensures that the provider's certificate was issued by a trusted certificate authority (CA) and prevents man-in-the-middle attacks.

When the provider uses a self-signed or internally-signed certificate that is not trusted by the system's CA bundle, all OIDC operations will fail with a TLS certificate verification error. The login page will display: *"TLS certificate verification failed. If the provider uses a self-signed certificate, enable 'Skip TLS certificate verification' in the identity provider settings."*

To allow connections to providers with untrusted certificates, enable **Skip TLS certificate verification** (`disable_tls_verify: true`) in the provider's OIDC configuration. This affects all outbound HTTPS connections for that provider:

- OIDC discovery (`.well-known/openid-configuration`)
- Token exchange
- JWKS key fetching (for ID token signature verification)
- Userinfo endpoint

**What is skipped**: All certificate verification — both CA trust-chain validation and hostname verification are disabled. Self-signed and internally-signed certificates are accepted regardless of the hostname they were issued for.

**What is NOT skipped**: TLS encryption is still active. The connection is encrypted.

**Security considerations**:

- Enabling this option reduces the security of the connection to the identity provider. Use it only when necessary (e.g., development environments, internal infrastructure with private CAs).
- When this setting is enabled, an audit event with WARNING severity is emitted on provider creation and update for security monitoring.
- The preferred production approach is to add the provider's CA certificate to the system trust store rather than disabling verification.

### PKCE

PKCE (Proof Key for Code Exchange) is always used for all OIDC flows, following OAuth 2.1 best practices. The backend generates a `code_verifier` and `code_challenge` (S256) for each login attempt. No provider-side configuration is needed — all major OIDC providers support PKCE.

### User Auto-Provisioning

When a user authenticates via OIDC and no `UserIdentity` exists for their `(issuer, sub)`:

1. The backend extracts `sub` and `email` claims from the ID token
2. A new user is auto-created with:
   - `username` from `preferred_username` claim (or email prefix). If taken, a 16-character random hex suffix is appended (e.g., `alice-a1b2c3d4e5f6g7h8`)
   - `email` from the `email` claim (must contain `@`). Duplicate emails are allowed across users.
   - `first_name` from the `given_name` claim (falls back to splitting `name`)
   - `last_name` from the `family_name` claim
   - `role` = `VIEWER` (default for auto-provisioned users)
   - `auth_type` = `'federated'`, `password_hash` = `null` (federated user, cannot use local login)
4. A `UserIdentity` row is created linking `(issuer, sub)` to the user
5. Disabled users (`is_enabled = false`) are rejected
6. If the linked user was deleted (stale identity), the identity is cleaned up and the flow restarts from step 2

### Claim Mapping

Different identity providers use different claim names for the same user information. For example, Azure AD uses `mail` for the email address, while the OIDC standard uses `email`. The `claim_mapping` configuration allows admins to map IdP-specific claim names to Nexus canonical fields.

#### Default mapping

| Nexus Field | Default Claim | Description |
|---|---|---|
| `subject` | `sub` | OIDC subject identifier |
| `email` | `email` | User's email address |
| `username` | `preferred_username` | Preferred username |
| `first_name` | `given_name` | User's first name |
| `last_name` | `family_name` | User's last name |
| `groups` | *(not mapped)* | Groups claim (must be explicitly configured) |

#### Example: Azure AD

```json
{
  "claim_mapping": {
    "email": "mail",
    "username": "upn",
    "first_name": "givenName",
    "last_name": "surname",
    "groups": "groups"
  }
}
```

When `groups` is set in the claim mapping, the groups claim is included in the extracted user claims. This is separate from `group_jmespath_expression` — `claim_mapping.groups` tells the backend *which claim name* contains groups, while `group_jmespath_expression` controls *how to extract values* from the raw token claims.

### OIDC Claim Sanitization

OIDC tokens from external identity providers may contain ASCII control characters (0x00–0x1F, 0x7F) in claim values — either through misconfiguration, encoding bugs, or malicious injection. Nexus applies a **tiered sanitization strategy** based on the sensitivity of each claim:

#### Strategy by claim type

| Claim type | Claims | Strategy | Rationale |
|---|---|---|---|
| **Identity** | `sub`, `email` | **Reject** — deny the login | These claims are used as identity keys (`user_identities` table is keyed on `(issuer, sub)`). Silently modifying them could collapse two distinct identities into one, causing an authorization bypass or account takeover. Rejection is the safest and most transparent response. |
| **Display** | `name`, `given_name`, `family_name`, `preferred_username` | **Escape** — replace control chars with visible escape sequences (e.g., `\n`, `\x00`) | These claims are used for display and auto-provisioning. Escaping preserves the original information in logs and stored values for diagnostics, without silently discarding characters. |
| **Group** | Group values extracted via JMESPath | **Escape** — same as display claims | Group values are matched against configured mapping entries for authorization. Stripping characters could silently alter group names, causing authorization bypass (a group name that should not match now matches after stripping) or silent denial (a legitimate group stops matching). Escaping preserves the original value for accurate matching and log transparency. |

#### Why not strip?

Stripping control characters silently discards information, which creates several risks:

- **Identity collision**: Two distinct `sub` values (e.g., `user\x00admin` and `useradmin`) collapse into the same value after stripping, potentially granting one user access to another's account.
- **Authorization bypass**: A group name containing control characters could match a different mapping entry after stripping, granting unintended group membership.
- **Lost diagnostics**: When investigating authentication issues, stripped values make it impossible to determine what the IdP actually sent.

#### Why not reject everything?

Rejecting all claims with control characters would be the strictest approach, but display claims (`name`, `preferred_username`) are not security-sensitive — they don't drive identity resolution or authorization decisions. Rejecting on these would unnecessarily block legitimate users whose IdP happens to include a stray control character in a display name. Escaping gives operators visibility into the issue without disrupting access.

#### Logging

All sanitization actions are logged at WARNING level with structured context:

- **Rejection** (identity claims): `"Rejected OIDC token: control characters in identity claim"` with `claim` and `escaped_value` fields. The escaped value shows the original content with control characters rendered as visible escape sequences for investigation.
- **Escaping** (display/group claims): `"Escaped control characters in OIDC claim"` with `claim` and `escaped_value` fields.

#### Implementation

Sanitization is applied in two places:

1. **`OIDCService.extract_user_claims()`** — processes `sub`, `email`, `name`, and `preferred_username` from the ID token / userinfo response. Identity claims trigger rejection; display claims are escaped.
2. **`extract_idp_group_values()`** — processes group values extracted by JMESPath from the raw merged claims. Control characters are escaped before group matching.

The sanitization utilities (`has_control_chars`, `escape_control_chars`) are in `syntara.core.lib.sanitization`.

### Test Sign-In Flow

Admins can test an OIDC provider's sign-in flow without creating a session. This is useful for verifying claim mapping and group mapping configurations against real IdP token claims.

```
Admin clicks "Test Sign-In" in the IdP configuration UI
  -> Browser opens popup to: GET /api/v1/auth/oidc/authorize?provider_id=X&flow=test_signin
  -> Backend verifies admin's session via ao_refresh_token cookie
  -> Normal OIDC flow proceeds (redirect to provider, callback)
  -> On callback, no session or user is created
  -> Backend base64-encodes the raw merged claims into a URL fragment
  -> Backend redirects popup to: {frontend_origin}/auth/test-signin-callback#{base64_claims}
  -> Frontend reads the hash, writes claims to localStorage, closes the popup
  -> Admin can inspect the raw claims to verify their configuration
```

The test sign-in flow requires authentication — only logged-in admins can initiate it. The claims are passed via URL fragment (not query parameters) to avoid server-side logging of sensitive claim data.

### Group Mapping and Login Enforcement

When a user authenticates via OIDC, Nexus determines which groups they belong to based on the identity provider's group mapping configuration. **If no groups can be resolved, login is denied** — the user sees an "Access denied" error on the login page.

#### How group resolution works

1. The backend extracts group values from the ID token using the configured JMESPath expression (e.g., `groups[*]`, `realm_access.roles[*]`)
2. Group values are matched against the mapping entries configured for that provider
3. Matched entries determine which Nexus groups the user is placed in
4. Groups are synced (session-scoped): all previous IdP-assigned group memberships are cleared, and only groups from the current login's token are assigned
5. Manually-assigned groups are never affected

#### Modes: manual mapping and allow all authenticated

- **Manual mapping** — Admins configure explicit mapping entries that map IdP group values to Nexus groups. Only matched entries grant group membership.
- **Allow all authenticated** — When `allow_all_authenticated` is enabled, all users from the IdP can log in regardless of group mapping results. They are added to the built-in `users` group and receive the implicit "authenticated" group (added automatically by the authz resolver). Group mappings can still be configured alongside this for more granular access.

Both modes respect the **JMESPath expression** configured on the provider. The expression is evaluated first to extract group values from the token claims, and only the extracted values are used for mapping. This means admins can use JMESPath to filter which groups are considered — for example, `groups[?starts_with(@, 'nexus-')]` would only extract groups prefixed with `nexus-`, ignoring all others in the token.

**JMESPath validation**: Expressions are validated at configuration time — saving an invalid expression (e.g., `[[[bad`) returns a 422 error. If a valid expression fails at runtime (e.g., unexpected token claim structure), the group sync is aborted and login is denied rather than silently removing the user's groups.

**Scalar claim mismatch**: If the JMESPath expression uses a wildcard projection (e.g., `groups[*]`) but the IdP sends the claim as a bare string instead of an array (e.g., `"groups": "admin"` instead of `"groups": ["admin"]`), login is denied with an error. The error log message instructs the administrator to either fix the IdP to send an array or remove the trailing `[*]` from the expression. This strict behavior avoids silently guessing the intended interpretation of the expression.

#### Push-Button AAP Setup

The `POST /identity_providers/setup-aap-oidc` endpoint automates the full AAP OIDC identity provider setup in a single API call. It connects to an AAP Gateway instance, creates an OAuth2 application, and configures the corresponding identity provider in Nexus with AAP-specific defaults.

**Request body:**

| Field | Required | Default | Description |
|---|---|---|---|
| `aap_url` | Yes | — | AAP Gateway base URL (e.g., `https://aap.example.com`) |
| `organization` | No | `"Default"` | AAP organization name to create the OAuth2 application in |
| `admin_username` | Yes | — | AAP platform admin username |
| `admin_password` | Yes | — | AAP platform admin password (used only for setup, never stored) |
| `insecure_skip_tls_verify` | No | `false` | Skip TLS certificate verification for the AAP connection |

**What happens when the endpoint is called:**

1. The backend resolves the AAP organization by name via `GET /api/gateway/v1/organizations/?name=<name>`.
2. An OAuth2 application named after `APP_PRODUCT_NAME` (defaults to "Syntara") is created on AAP via `POST /api/gateway/v1/applications/` using the admin credentials. The redirect URI is derived from `APP_SERVER_PUBLIC_URL`.
3. An identity provider is created in Nexus with the following AAP preset defaults:
   - `idp_type` = `"aap"`, `auto_discovery` = `true`
   - `issuer_url` = `{aap_url}/o/`
   - `scopes` = `"read write openid roles"`
   - JMESPath group extraction for AAP teams and organizations
   - `aap_role_mapping_enabled` = `true` (see [AAP Role Mapping](#aap-role-mapping))
   - `enable_rp_initiated_logout` = `true`
   - `disable_tls_verify` mirrors the request's `insecure_skip_tls_verify` value
4. The created identity provider is returned (201).

**Prerequisites:**

- `APP_SERVER_PUBLIC_URL` must be set to the frontend URL so the OAuth2 redirect URI is correct.
- The admin credentials must have permission to create applications in the specified organization.

**Error cases:**

| Scenario | HTTP Status | Error |
|---|---|---|
| AAP unreachable or timeout | 502 | `AAPConnectionError` |
| TLS verification failure | 502 | `AAPConnectionError` (with suggestion to enable TLS skip) |
| Invalid credentials | 502 | `AAPAuthenticationError` |
| Insufficient privileges | 502 | `AAPAuthenticationError` |
| Organization not found | 502 | `AAPSetupError` |
| Duplicate OAuth2 app name | 502 | `AAPSetupError` (with suggestion to delete existing app or configure manually) |

**Security notes:**

- The `admin_password` is used only for the one-time API calls to create the OAuth2 application and is never persisted.
- The `aap_url` is validated against SSRF (private network) restrictions.

#### AAP Role Mapping

When an AAP provider template is used (`idp_type: "aap"`), administrators can enable `aap_role_mapping_enabled` to automatically map the AAP `aap_system_role` claim to built-in Nexus groups. This is enabled by default in the UI when the AAP template is selected.

The mapping uses the `aap_system_role` string claim from the AAP OIDC token:

| `aap_system_role` value | Mapped Group |
|---|---|
| `system_administrator` | `admins` |
| `system_auditor` | `auditors` |
| `normal_user` / other / missing | `users` |

**Key behaviors:**

- **Additive**: AAP role mapping runs alongside JMESPath/manual group mapping. The groups it resolves are merged with whatever the existing mapping produces.
- **AAP-only**: The mapping only activates when both `aap_role_mapping_enabled` is `true` and `idp_type` is `"aap"`. Setting the flag on a custom provider has no effect.
- **String matching**: The `aap_system_role` claim must be an exact string match (`"system_administrator"`, `"system_auditor"`). Unrecognised values or non-string types fall back to the `users` group.
- **Always resolves a group**: Because the fallback is `users`, AAP role mapping always produces at least one group membership. This means login is never denied due to missing group mappings when AAP role mapping is enabled — even if a co-configured JMESPath expression fails at runtime, AAP role mapping still proceeds independently.
- **Built-in groups only**: The mapping targets the seeded built-in groups (`admins`, `auditors`, `users`) by name and `is_builtin=True`, preventing collisions with user-created groups of the same name.

#### Login denial rules

Login is denied if no groups can be resolved for the user from any source.

**Manual mapping mode:**

| Mapping entries exist? | Any match? | Manual groups exist? | Result |
|---|---|---|---|
| No | n/a | No | **Denied** |
| No | n/a | Yes | Allowed |
| Yes | Yes | n/a | Allowed |
| Yes | No | No | **Denied** |
| Yes | No | Yes | Allowed |

**Allow all authenticated mode** (`allow_all_authenticated: true`):

| Mapping entries exist? | Any match? | Result |
|---|---|---|
| No | n/a | Allowed (user gets built-in "users" group + implicit "authenticated" group) |
| Yes | Yes | Allowed (user gets matched groups + built-in "users" group + implicit "authenticated" group) |
| Yes | No | Allowed (user gets built-in "users" group + implicit "authenticated" group; stale IdP groups cleared) |

**Key points:**

- A user is only allowed to log in if they end up with at least one group membership — either from the current provider or from another source (manual assignment, another IdP).
- **Allow all authenticated** grants unconditional login access. Users are added to the built-in `users` group and also receive the implicit "authenticated" group from the authz resolver. Group mappings still sync normally if configured. If a JMESPath expression fails at runtime, login is still allowed — the user gets the `users` and "authenticated" groups but no claim-based groups are synced.
- **No mappings configured** (and `allow_all_authenticated` off) means the provider cannot assign groups, so login is denied for users with no pre-existing group memberships.
- "Other group sources" means: groups assigned manually by an admin, or groups assigned by a different identity provider.
- The denial message shown to the user is: *"Access denied. Your identity provider groups do not match any configured group mappings. Contact your administrator."*

#### Wildcard patterns in mapping entries

The IdP Group Value field supports glob-style wildcard patterns (Python `fnmatch` syntax):

| Pattern | Matches | Example |
|---|---|---|
| `*` | Everything — all users from this IdP | Maps everyone to a default group |
| `admin*` | Any value starting with "admin" | `admin-prod`, `admin-staging` |
| `*/engineers` | Path patterns | `org1/engineers`, `org2/engineers` |
| `team-?` | Single character wildcard | `team-a`, `team-b` (not `team-ab`) |

Wildcards are evaluated at login time when matching the user's IdP group values against configured mapping entries.

**Note:** A bare `*` mapping unconditionally matches — it adds the target group even when the user's token contains no group claims (empty or missing). This makes `*` effectively an "allow everyone" mapping for a specific group. For broader unconditional access without needing a mapping entry, use `allow_all_authenticated` instead.

#### Group mapping storage

Mapping entries are stored in the `idp_group_mapping_entries` table (not in JSONB). Each entry has:

- `identity_provider_id` — FK to `identity_providers` (CASCADE on delete)
- `idp_group_value` — the pattern to match (exact or wildcard)
- `nexus_group_id` — FK to `groups` (CASCADE on delete)
- Unique constraint on `(identity_provider_id, idp_group_value)`

Deleting a group automatically removes any mapping entries pointing to it. Deleting a provider removes all its mapping entries.

#### Tracking table: `user_idp_groups`

A separate `user_idp_groups` table tracks which groups the most recent IdP login assigned to the user. Group sync is session-scoped — on login, all previous IdP-assigned group memberships are cleared and replaced with groups from the current login's token. Groups assigned manually by an admin are never touched.

#### Multiple sessions from different IdPs

A user can have multiple active sessions from different identity providers (e.g., one session from Azure and another from Okta). Group sync follows a **last-login-wins** model: the user's IdP-managed group memberships always reflect the most recent login, regardless of which session is being used.

**Example scenario:**

1. User logs in via Azure — groups set to `["admins"]` (from Azure mapping)
2. User logs in via Okta — groups overwritten to `["developers"]` (from Okta mapping)
3. User refreshes the Azure session — the access token contains `idp="Azure"` but the groups are `["developers"]` (from the Okta login in step 2), because `POST /auth/refresh` reads group memberships from the user-level `user_groups` table

This is intentional. Group memberships are stored at the user level, not per-session. The session-scoped sync model prevents over-provisioning (which would occur if groups from all IdPs were merged), and a single consistent view of the user's permissions avoids the confusion of having different permissions in different browser tabs.

Manually-assigned groups are unaffected by this behavior — they persist across all IdP logins.

#### Membership sources in API responses

The group membership endpoints return enriched responses that indicate *how* each membership was established:

- **`GET /users/{id}/groups`** returns `UserGroupRead` objects — each group includes a `membership_sources` list.
- **`GET /groups/{id}/members`** returns `GroupMemberRead` objects — each user includes a `membership_sources` list.

Each `MembershipSource` has:

| Field | Description |
|---|---|
| `type` | `"manual"` (admin-assigned) or `"idp"` (assigned by an identity provider) |
| `provider_name` | Name of the IdP (only for `type: "idp"`) |
| `provider_id` | UUID of the IdP (only for `type: "idp"`) |

A user can have multiple sources for the same group (e.g., manually assigned *and* assigned by an IdP). Group sync is session-scoped: on each login, all previous IdP-assigned memberships are replaced with those from the current token. Manually-assigned memberships are never affected by IdP sync.

### User API Response

The `UserRead` response schema includes:

- **`is_enabled`** — whether the user account is enabled (renamed from `is_active`)
- **`is_builtin`** — whether this is a built-in user (e.g., the seeded admin). Built-in users have special protection rules (see [Built-in Admin Protection](#built-in-admin-protection)).
- **`auth_type`** — `"local"` or `"federated"`. Determines whether the user authenticates via local password or an external identity provider. These are mutually exclusive (enforced by a database CHECK constraint).

### `user_identities` Table

| Column | Type | Description |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → `users.id` (ON DELETE CASCADE) |
| `identity_provider_id` | UUID | FK → `identity_providers.id` (ON DELETE CASCADE) |
| `issuer` | VARCHAR(2048) | OIDC issuer URL |
| `subject` | VARCHAR(1024) | OIDC `sub` claim |
| `created_at` | TIMESTAMPTZ | When the identity was linked |
| `updated_at` | TIMESTAMPTZ | When the identity was last updated (e.g., re-attached) |
| `last_used_at` | TIMESTAMPTZ | When the identity was last used to authenticate (nullable) |

**Constraint**: `UNIQUE(issuer, subject)` — each `(issuer, sub)` pair can only be linked to one user.

### Local / Federated User Types

Users are one of two types, enforced at the database level:

| Auth Type | `auth_type` | `password_hash` | `user_identities` rows | Can log in via |
|-----------|-------------|-----------------|------------------------|----------------|
| Local | `'local'` | Set (Argon2id) | None | Username + password |
| Federated | `'federated'` | `NULL` | One or more | OIDC identity provider |

A `CHECK` constraint on the `users` table enforces this invariant:

```sql
(auth_type = 'local' AND password_hash IS NOT NULL)
OR (auth_type = 'federated' AND password_hash IS NULL)
```

**Local-to-federated conversion:** Non-builtin local users can link an identity provider. When they do, the user is permanently converted to federated: `auth_type` is set to `'federated'`, `password_hash` is cleared, all sessions are revoked, and the user's `token_version` is incremented to immediately invalidate any outstanding access tokens. This is a one-way conversion — federated users cannot set a password. Built-in users (e.g., the seeded admin) cannot link identity providers.

**Enforcement points:**

| Action | Guard | Error Code |
|--------|-------|------------|
| Set password on federated user (`PATCH /users/{id}`) | `PasswordOnFederatedUserError` | `PASSWORD_ON_FEDERATED_USER` (409) |
| Attach identity to built-in user (`POST /users/{id}/identities`) | `IdentityOnBuiltinUserError` | `IDENTITY_ON_BUILTIN_USER` (409) |
| Self-service OIDC link for built-in user | `OIDCError` | Redirects with `link_error` param |

OIDC auto-created users are always created with `auth_type = 'federated'`. Users created via `POST /users` (with a password) are always `auth_type = 'local'`.

### Self-Service Identity Linking

Users can link OIDC identities to their account from the **User Detail > Identities** tab. Local users see a conversion warning before linking — the action permanently removes their password and converts them to a federated account. Built-in users cannot link identity providers.

```
User clicks "Connect" on an unlinked provider
  -> Browser navigates to: GET /api/v1/auth/oidc/authorize?provider_id=X&flow=link&redirect_to=...
  -> Backend verifies the user's session via ao_refresh_token cookie
  -> Backend encodes flow_type="link" and user_id in encrypted state parameter
  -> OIDC flow proceeds normally (redirect to provider, callback)
  -> On callback, backend creates a UserIdentity for the authenticated user
  -> No new session is created (user is already logged in)
  -> Backend redirects back to the identities page
```

If the identity `(issuer, sub)` is already linked to another account, the flow returns a `link_error` and the UI displays a notification.

### Identity Lifecycle

- **last_used_at** — updated on each OIDC login and on initial link, tracked per identity
- **Disconnect** — users can disconnect their own identities (unless it's their only sign-in method and they have no password). All sessions are revoked and `token_version` is incremented
- **Attach/Detach** — admins can manually move identities between users via the Attach Identity modal. On attach, sessions are revoked and `token_version` is incremented for both source and target users. On detach, sessions are revoked and `token_version` is incremented for the affected user
- **Provider deletion** — deleting an identity provider bulk-deletes all linked user identities and revokes active sessions authenticated via that provider (indexed by provider ID for efficient lookup)
- **User disabled/deleted** — disabling or soft-deleting a user immediately revokes all their active sessions (see [Session Revocation](#session-revocation))

### Token Claims for Federated Users

Access tokens for OIDC-authenticated users include:

- `amr` = `["fed"]` — authentication method reference (federated)
- `idp` = provider name (e.g., `"Azure"`, `"Okta"`)
- `role` = user's role from the database

These values are preserved across token refreshes via session metadata stored in the `refresh_sessions` table.

### Test Connection

The `POST /test` endpoint accepts a full provider creation payload and fetches `{issuer_url}/.well-known/openid-configuration` to verify the OIDC provider is reachable and returns the required fields (`authorization_endpoint`, `token_endpoint`, `issuer`, `jwks_uri`). No data is persisted.

On success, the response also includes:

- `claims_supported` — list of claim names the provider advertises (from the discovery document's `claims_supported` field). Useful for configuring `claim_mapping`.
- `claim_aliases` — a mapping of Nexus field names to common IdP claim aliases (e.g., `email` → `["mail", "upn", "preferred_username"]`). Helps the UI suggest claim mappings for the selected provider type.

## Configuration Reference

| Environment Variable | Default | Description |
|---|---|---|
| `APP_JWT_PRIVATE_KEY_PATH` | — | Path to ES256 private key PEM file |
| `APP_JWT_PRIVATE_KEY_BASE64` | — | Base64-encoded ES256 private key PEM |
| `APP_JWT_KEY_ID` | `nexus-primary` | Key ID (`kid`) in JWT header |
| `APP_JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `15` | Access token lifetime |
| `APP_JWT_REFRESH_TOKEN_LIFETIME_HOURS` | `8` | Refresh token lifetime |
| `APP_JWT_BACKUP_KEYS` | — | JSON list of backup keys for rotation |
| `APP_ADMIN_PASSWORD_PATH` | — | Path to file containing bootstrap admin password (migration skips seeding if unset; can also use `uv run python tools/set_admin_password.py`) |
| `APP_ADMIN_PASSWORD` | — | Admin password value (used by `generate_secrets.sh` only) |
| `APP_SERVER_SCHEME` | `https` | URL scheme for the constructed server URL (`https` for production, `http` for local dev). Used in the JWT issuer and post-logout redirect when `APP_SERVER_PUBLIC_URL` is not set. Also controls the `Secure` flag on the refresh cookie (HTTPS → `Secure=true`, HTTP → `Secure=false`) |
| `APP_SERVER_PUBLIC_URL` | — | Public base URL for this Nexus instance (e.g., `https://example.com:8000`). Must be a valid URL. Used as the JWT issuer (`iss` claim), post-logout redirect, and frontend origin fallback. If not set, falls back to `{APP_SERVER_SCHEME}://{APP_SERVER_HOST}:{APP_SERVER_PORT}`. Required when the server binds to `0.0.0.0` or runs behind a reverse proxy |
| `APP_COOKIE_DOMAIN` | — | `Domain` attribute for refresh cookie |
| `APP_CORS_ALLOW_ORIGINS` | `[]` | Allowed origins for CORS and OIDC redirect validation. Wildcard `*` is rejected when credentials are enabled |
| `APP_CORS_ALLOW_CREDENTIALS` | `true` | Allow credentials (cookies) in CORS requests |
| `APP_CORS_ALLOW_METHODS` | `["GET","POST","PUT","PATCH","DELETE","OPTIONS"]` | Allowed HTTP methods for CORS |
| `APP_CORS_ALLOW_HEADERS` | `["Authorization","Content-Type","Accept"]` | Allowed headers for CORS |
| `APP_OIDC_ALLOW_PRIVATE_NETWORKS` | `false` | Allow OIDC providers on private/internal networks. Enable for environments with internal IdPs (e.g., corporate Keycloak). When disabled, issuer URLs resolving to private/loopback IPs are rejected |
| `APP_OIDC_POST_LOGOUT_REDIRECT_URI` | *(computed)* | Global post-logout redirect URI for RP-initiated logout. Priority: this setting > `APP_SERVER_PUBLIC_URL` > `{scheme}://{host}:{port}`. Must be an allowed CORS origin |
| `APP_SECRET_ENCRYPTION_KEY` | `"0" * 64` (dev only) | 64-character hex string (32 bytes) for AES-256-GCM encryption of sensitive fields (e.g., OIDC client secrets, credentials). **Must** be set to a secure random value in production |

> **Tip**: Copy `.env.example` to `.env` for local development — it includes all auth-related settings pre-configured with paths to the generated secrets (e.g., `APP_JWT_PRIVATE_KEY_PATH=.secrets/jwt-primary.pem`) and `APP_SERVER_SCHEME=http` (which also disables the `Secure` cookie flag for local HTTP).
