# Service Accounts

This document describes the OAuth 2.0 service accounts feature for machine-to-machine authentication in Syntara. It is intended for developers working on the project and is updated as each piece of the feature lands.

For human-user authentication (login, OIDC, sessions, CSRF), see [authentication.md](authentication.md).

## Overview

Service accounts enable programmatic API access without interactive user login. They use the OAuth 2.0 **client credentials grant** (RFC 6749 §4.4) — a client authenticates with a `client_id` and `client_secret`, and receives a short-lived JWT access token.

Use cases include CI/CD pipelines triggering workflows, ITSM platforms initiating remediation, partner systems exchanging data, monitoring tools invoking automated responses, and **Event-Driven Ansible (EDA) triggering workflows via webhooks**.

### How it differs from human authentication

| Concern | Human auth | Service accounts |
|---------|-----------|-----------------|
| Flow | Browser redirect, cookies, PKCE | `POST /api/v1/auth/token` with client credentials |
| Session storage | PostgreSQL `refresh_sessions` | None — stateless JWT only |
| Token refresh | `POST /auth/refresh` with cookie | Not supported — request a new token |
| CSRF protection | Required (cookie-based auth) | N/A (bearer token only) |
| Identity providers | OIDC federation, claim mapping | N/A |
| Secret storage | Argon2id password hash on `users` | Argon2id secret hash on `service_account_credentials` |
| Token lifetime | Configurable via `jwt_access_token_lifetime_minutes` | Configurable via `jwt_sa_access_token_lifetime_minutes` (default 15 min, max 60) |
| WebSocket access | Supported via ws-ticket exchange | Blocked — returns 403 |
| Deletion | Soft-delete | Hard-delete (cascades credentials and role assignments) |

### Shared infrastructure

Service accounts reuse the same JWT signing infrastructure as human authentication:

- **ES256 key pair** — same `TokenService` and `KeyManager` (see [Key Management](authentication.md#key-management))
- **Token validation** — same middleware validates signatures and checks `exp`
- **Global revocation** — the global revocation timestamp applies to service account tokens (see [Global Token Revocation](authentication.md#global-token-revocation))

## Data Model

### `service_accounts` table

The `ServiceAccount` model (`src/syntara/service_accounts/models/service_account.py`) inherits from `NamedResource` and `UserOwnedResource`. It uses hard deletion — there are no `deleted_at` or `deleted_by` columns.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK, FK → `principals`) | Auto-generated primary key |
| `name` | VARCHAR(255) | Human-readable name |
| `description` | VARCHAR(2000) | Optional description |
| `status` | CHECK constraint (`active`, `disabled`) | Operational status |
| `project_id` | UUID (FK → `projects`) | Project namespace for resource isolation |
| `token_version` | INT, default 0 | Incremented on disable to invalidate issued tokens |
| `last_authenticated_at` | TIMESTAMPTZ, nullable | Timestamp of the most recent successful authentication |
| `created_by` | UUID (FK → `principals`) | User who created the service account |
| `updated_by` | UUID (FK → `principals`, nullable) | User who last modified the service account |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last modification timestamp |
| `labels` | JSONB | Key-value metadata (standard across all resources) |

**Indexes:**

- `ix_service_accounts_created_at_id` — composite index for cursor-based pagination
- Individual indexes on `status`, `project_id`, `name`, `created_by`, `updated_by`

**Audit level:** `META` — audit events capture metadata fields only.

**Principal integration:** A `Principal` row is auto-created via a SQLAlchemy `_before_flush` session listener whenever a `ServiceAccount` is added to the session. The service account and principal share the same UUID primary key.

### `service_account_credentials` table

The `ServiceAccountCredential` model (`src/syntara/service_accounts/models/service_account_credential.py`) extends `UserOwnedResource`. Credentials are a sub-resource of service accounts, supporting multiple credentials per account.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID (PK) | Auto-generated primary key |
| `service_account_id` | UUID (FK → `service_accounts`, CASCADE) | Parent service account |
| `credential_type` | CHECK constraint (`client_credentials`) | Type of credential |
| `identifier` | VARCHAR(64), UNIQUE | Public identifier (e.g., `client_id`) |
| `hashed_secret` | TEXT | Argon2id hash of the secret |
| `old_hashed_secret` | TEXT, nullable | Previous secret hash during rotation grace period |
| `old_secret_valid_until` | TIMESTAMPTZ, nullable | When the old secret stops being accepted |
| `grace_period_seconds` | INT, default 3600 (0–86400) | How long the old secret remains valid after rotation |
| `status` | CHECK constraint (`active`, `disabled`) | Operational status |
| `expires_at` | TIMESTAMPTZ, nullable | Optional expiry timestamp (capped by `service_accounts.credential_max_lifetime_days` runtime setting) |
| `last_used_at` | TIMESTAMPTZ, nullable | Timestamp of last use |
| `created_by` | UUID (FK → `principals`) | User who created the credential |
| `updated_by` | UUID (FK → `principals`, nullable) | User who last modified the credential |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last modification timestamp |
| `labels` | JSONB | Key-value metadata |

The `service_account_id` FK uses `CASCADE` on delete — when a service account is deleted, all its credentials are automatically removed.

**Indexes:**

- `ix_sa_credentials_identifier_unique` — unique index on `identifier`
- `ix_sa_credentials_sa_id_type` — composite index on `(service_account_id, credential_type)`
- `ix_sa_credentials_created_at_id` — composite index for cursor-based pagination

**Audit level:** `META` — `hashed_secret` and `old_hashed_secret` are excluded from audit logs.

**Limit:** Maximum 10 credentials per service account (enforced by `MAX_CREDENTIALS_PER_SA` in `constants.py`).

### `webhook_trigger_service_accounts` table

The `WebhookTriggerServiceAccount` model (`src/syntara/workflows/models/webhook_trigger_service_account.py`) is a many-to-many association table that binds service accounts to webhook triggers. Only explicitly bound service accounts can invoke a given trigger.

| Column | Type | Description |
|--------|------|-------------|
| `webhook_trigger_id` | UUID (PK, FK → `webhook_triggers`, CASCADE) | Webhook trigger |
| `service_account_id` | UUID (PK, FK → `service_accounts`, CASCADE) | Authorized service account |

Both FKs use `CASCADE` on delete — when either a trigger or service account is deleted, the binding is automatically removed.

**Indexes:**

- `ix_wt_sa_service_account_id` — index on `service_account_id` for reverse lookups

### Credential types

| Type | Identifier format | Secret format | Use case |
|------|------------------|---------------|----------|
| `client_credentials` | `nx_sa_{uuid4_hex[:16]}` | `token_urlsafe(48)` (64 chars) | OAuth 2.0 client credentials grant |

### Secret hashing

Secrets are hashed with **Argon2id** using the same `hash_password` / `verify_password` utilities as user passwords (`src/syntara/auth/passwords.py`). The plaintext secret is displayed exactly once at creation time and cannot be retrieved afterward.

## CRUD API

### Service account endpoints

All endpoints live under `/api/v1/service_accounts`. Project scoping is enforced via `project_id` in the request body (create) and `VisibilityFilter` (list). All endpoints use `PermissionChecker` per action.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/service_accounts` | Create a service account |
| `GET` | `/service_accounts` | List service accounts (paginated, filterable, project-scoped) |
| `GET` | `/service_accounts/{service_account_id}` | Get service account details |
| `PATCH` | `/service_accounts/{service_account_id}` | Update name and/or description |
| `DELETE` | `/service_accounts/{service_account_id}` | Hard-delete a service account (cascades credentials and role assignments) |
| `POST` | `/service_accounts/{service_account_id}/enable` | Set status to `active` |
| `POST` | `/service_accounts/{service_account_id}/disable` | Set status to `disabled` and increment `token_version` (invalidates outstanding tokens) |

### Credential endpoints

Credentials are nested sub-resources of service accounts. Permissions inherit from the parent service account.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/service_accounts/{sa_id}/credentials` | Create a credential (201, returns one-time secret) |
| `GET` | `/service_accounts/{sa_id}/credentials` | List credentials (paginated) |
| `GET` | `/service_accounts/{sa_id}/credentials/{cred_id}` | Get credential details |
| `DELETE` | `/service_accounts/{sa_id}/credentials/{cred_id}` | Hard-delete a credential (204) |
| `POST` | `/service_accounts/{sa_id}/credentials/{cred_id}/rotate` | Rotate secret |
| `POST` | `/service_accounts/{sa_id}/credentials/{cred_id}/disable` | Disable credential |
| `POST` | `/service_accounts/{sa_id}/credentials/{cred_id}/enable` | Enable credential |

### Create flow

```
1. Admin creates a service account:
   POST /api/v1/service_accounts
   { "name": "CI Pipeline", "description": "...", "project_id": "..." }
   -> 201 with service account details (no credentials yet)

2. Admin creates a credential for the service account:
   POST /api/v1/service_accounts/{sa_id}/credentials
   { "credential_type": "client_credentials" }
   -> 201 with credential details + plaintext client_secret
   -> ⚠️ Secret is shown ONCE — it cannot be retrieved again
```

### Delete behavior

Service accounts use **hard deletion**. When a service account is deleted:

1. All credentials are deleted (via FK CASCADE)
2. All non-builtin role assignments for the SA are deleted
3. All webhook trigger bindings are deleted (via FK CASCADE)
4. The service account row is deleted
5. The `Principal` row is **preserved** for FK integrity (other tables reference `created_by` / `updated_by`)

### One-time secret display

On creation and rotation, the plaintext secret is returned in the response body exactly once. The backend stores only the Argon2id hash. If the secret is lost, the only option is to rotate to a new one.

## Secret Rotation

### Grace period

When a credential's secret is rotated, both the old and new secrets are accepted for a configurable grace period. This prevents downtime when multiple consumers of the secret need time to update.

```
POST /api/v1/service_accounts/{sa_id}/credentials/{cred_id}/rotate
  { "grace_period_seconds": 7200 }   (optional override)

Rotation:
  -> Backend generates new secret, hashes it
  -> Backend moves current hashed_secret → old_hashed_secret
  -> Backend sets old_secret_valid_until = now() + grace_period_seconds
  -> Backend stores new hash in hashed_secret
  -> Backend returns new plaintext secret (one-time display)

Authentication during grace period (client submits a secret without indicating which one):
  1. Verify against hashed_secret (current) → if match, accept
  2. If no match, check old_hashed_secret is non-null and old_secret_valid_until > now()
  3. If yes, verify against old_hashed_secret → if match, accept
  4. Otherwise reject

After grace period expires:
  -> Step 2 fails the time check, so only the current secret is accepted
  -> Backend clears old_hashed_secret and old_secret_valid_until on next auth attempt
```

The default grace period is 3600 seconds (1 hour), configurable per credential via the `grace_period_seconds` field.

## Client Credentials Grant

### Token endpoint

```
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=nx_sa_...&client_secret=...
```

Alternatively, credentials can be provided via HTTP Basic authentication (RFC 6749 §2.3.1):

```
POST /api/v1/auth/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

### Response

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900
}
```

No refresh token is issued. When the access token expires, the client requests a new one.

### Token claims

Service account access tokens include:

| Claim | Description |
|-------|-------------|
| `sub` | Service account UUID |
| `iss` | Syntara server URL (same issuer as human tokens) |
| `aud` | Token audience |
| `iat` | Issued-at timestamp |
| `exp` | Expiration timestamp |
| `token_type` | `"service_account"` (distinguishes from human tokens) |
| `preferred_username` | Service account name |
| `groups` | Always `[]` — SAs get permissions via direct role assignments, not group membership |
| `token_ver` | Token version counter (for stale-token detection by middleware) |
| `cred_id` | Credential UUID that issued this token (for per-credential revocation) |

Service account tokens **omit** `amr`, `idp`, `email`, `name`, `given_name`, and `family_name` claims.

### Validation

The token endpoint validates credentials in a timing-safe manner:

1. Look up `ServiceAccountCredential` joined with `ServiceAccount` by `client_id`
2. If unknown `client_id`, perform a dummy Argon2 verify (constant-time) before rejecting
3. Verify secret against `hashed_secret`, falling back to `old_hashed_secret` during grace period
4. All status checks (SA disabled, credential disabled, credential expired) are evaluated before branching to prevent timing side-channels
5. On success, update `last_authenticated_at` on SA and `last_used_at` on credential

### Rejection rules

| Condition | Response |
|-----------|----------|
| Unknown `client_id` | 401 `invalid_client` |
| Secret does not match current or previous (non-expired) hash | 401 `invalid_client` |
| Service account status is `disabled` | 401 `invalid_client` |
| Credential status is `disabled` | 401 `invalid_client` |
| Credential is expired | 401 `invalid_client` |
| Unsupported `grant_type` | 400 `unsupported_grant_type` |

All rejection responses use the same generic error to avoid leaking whether a `client_id` exists (enumeration protection).

### WebSocket restriction

Service account tokens cannot be exchanged for WebSocket tickets. `POST /auth/ws-ticket` returns 403 with code `SERVICE_ACCOUNT_WS_TICKET_FORBIDDEN` and header `X-Auth-Failure-Type: service_account_forbidden`.

## Auth Middleware Integration

The `StaleTokenMiddleware` (`src/syntara/auth/middleware.py`) handles service account tokens alongside user tokens. When it encounters a JWT with `token_type: "service_account"`, it runs two check phases via `_handle_sa_token()`:

**Phase 1 — SA identity (`_check_sa_identity`):**

```
_check_sa_status(sa_id) — raw SQL with 5s TTL cache

  1. SA not found (deleted)?
     -> 401, code=SA_DELETED, X-Auth-Failure-Type: deleted_sa
     -> Dispatch DisabledSARejectionEvent(is_alive=False)

  2. SA status != "active" (disabled)?
     -> 401, code=SA_DISABLED, X-Auth-Failure-Type: disabled_sa
     -> Dispatch DisabledSARejectionEvent(is_alive=True)

  3. token_ver < current token_version (stale)?
     -> 401, code=SA_TOKEN_REVOKED, X-Auth-Failure-Type: revoked_sa_token
     -> Dispatch StaleSATokenDetectionEvent (throttled to 1/min per SA)
```

**Phase 2 — credential (`_check_sa_credential`):**

```
  4. Token missing cred_id claim?
     -> 401, code=SA_TOKEN_REVOKED, X-Auth-Failure-Type: revoked_sa_token
     -> Dispatch MissingSACredentialClaimEvent

  5. _check_cred_status(cred_id) — raw SQL with 5s TTL cache (fetches status + expires_at)
     Credential not found (deleted) or status != "active" (disabled)?
     -> 401, code=SA_CREDENTIAL_DISABLED, X-Auth-Failure-Type: disabled_sa_credential
     -> Dispatch DisabledSACredentialRejectionEvent

  6. Credential expires_at is set and now >= expires_at?
     -> 401, code=SA_CREDENTIAL_EXPIRED, X-Auth-Failure-Type: expired_sa_credential
     -> Dispatch ExpiredSACredentialRejectionEvent
```

All rejection responses use RFC 9457 Problem Details format.

### Token version mechanism

The `token_version` column on the `service_accounts` table works with the `token_ver` JWT claim:

- When a SA is **disabled**, `token_version` is atomically incremented
- The middleware compares the JWT's `token_ver` against the current `token_version`
- If `token_ver < token_version`, the token is rejected as revoked
- This provides immediate invalidation of all outstanding tokens on disable

### Per-credential revocation

The `cred_id` JWT claim enables per-credential invalidation:

- Each SA token embeds the UUID of the credential that was used to obtain it
- The middleware checks the credential's status and `expires_at` via `_check_cred_status()` (5s TTL cache)
- Disabling, deleting, or letting a credential expire immediately invalidates only tokens from that credential — other credentials on the same SA remain unaffected
- Tokens without a `cred_id` claim are rejected outright (no backward compatibility)

### Caching

Status checks use in-process `TTLCache` to avoid a DB query on every request:
- `_sa_status_cache` — 5s TTL, maxsize 4096
- `_cred_status_cache` — 5s TTL, maxsize 4096
- `_stale_audit_cache` — 60s TTL for throttling audit events

## Authorization (RBAC)

### PrincipalType

The `PrincipalType` enum (`src/syntara/core/models/principal.py`) includes `SERVICE_ACCOUNT` as a first-class principal type alongside `USER`, `SERVICE`, and `SYSTEM`.

### Resource permissions

Service accounts are registered as an authz resource type in `src/syntara/authz/role_conventions.py`:

| Permission | Scope | Roles |
|------------|-------|-------|
| `service_account:create` | System | `admin` |
| `service_account:read` | System | `admin`, `auditor` |
| `service_account:update` | System | `admin` |
| `service_account:delete` | System | `admin` |
| `service_account:rotate_secret` | System | `admin` |
| `service_account:disable` | System | `admin` |
| `service_account:enable` | System | `admin` |
| `service_account:create` | Project | `project-admin` |
| `service_account:read` | Project | `project-admin`, `project-auditor` |
| `service_account:update` | Project | `project-admin` |
| `service_account:delete` | Project | `project-admin` |
| `service_account:rotate_secret` | Project | `project-admin` |
| `service_account:disable` | Project | `project-admin` |
| `service_account:enable` | Project | `project-admin` |

### Role assignments for service accounts

Service accounts can receive role assignments via the standard role assignment API. The `RoleAssignment` model uses `principal_id` (FK → `principals`), which supports both users and service accounts. The authz resolver (`src/syntara/authz/resolver.py`) resolves effective policies generically via `principal_id`.

The role assignment service (`src/syntara/authz/services/role_assignment_service.py`) handles the `"service_account"` principal type: it validates the SA exists, resolves its name for display, and outer-joins the `ServiceAccount` table in queries.

## Webhook and EDA Integration

Service accounts are the required authentication mechanism for webhook and EDA trigger endpoints. External systems (GitHub, Jira, Slack, EDA, etc.) must present a valid service account Bearer token to invoke a trigger.

### Trigger endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhooks/{webhook_path}` | Receive a webhook event and trigger the matching workflow |
| `POST` | `/webhooks/eda/{webhook_path}` | Receive an EDA webhook event and trigger the matching workflow |

Both endpoints:
1. Require a service account Bearer token (401 if missing/invalid or not a SA token)
2. Verify the SA is authorized for the specific trigger via the binding table (403 if not bound)
3. Dispatch audit events on success/failure
4. Start a workflow execution with the webhook payload as input

### Per-trigger SA binding

Each webhook/EDA trigger has an explicit list of authorized service accounts. This binding is managed as part of the workflow definition:

- `WebhookTriggerParameters` includes an `authorized_service_account_ids` field
- During workflow save, `_sync_trigger_sa_bindings()` syncs the desired SA IDs against existing bindings (computes add/remove sets)
- All bound SAs must exist in the same project as the workflow
- The `webhook_trigger_service_accounts` association table stores the bindings

### Authentication flow

```
External system (e.g., EDA rulebook action) sends:
  POST /api/v1/webhooks/eda/{path}
  Authorization: Bearer <sa_access_token>
  Content-Type: application/json

  { "event": { ... } }

  -> get_webhook_caller() dependency:
     1. Decode Bearer token via TokenService
     2. Check global revocation
     3. Verify token_type == "service_account"
     4. Return (User, service_account_id)

  -> _handle_webhook_request():
     1. Look up WebhookTrigger by path and type
     2. verify_service_account_authorization(trigger_id, sa_id)
        -> Checks webhook_trigger_service_accounts binding
        -> 403 WebhookServiceAccountNotAuthorizedError if not bound
     3. Dispatch WebhookAuthSuccessEvent
     4. Start workflow execution via ExecutionService

  -> 202 Accepted { "execution_id": "...", "message": "..." }
```

### EDA usage pattern

For Event-Driven Ansible integration, the typical setup is:

1. Create a service account in the same project as the workflow
2. Create a credential for the SA and store the `client_id` / `client_secret`
3. Configure the workflow's EDA trigger node with the SA in `authorized_service_account_ids`
4. In the EDA rulebook, use `run_workflow_template` (or a webhook URL action) that:
   - Obtains a token: `POST /api/v1/auth/token` with the SA credentials
   - Invokes the trigger: `POST /api/v1/webhooks/eda/{path}` with the Bearer token

### Payload limits

Webhook payloads are limited to 1 MB (`WebhookLimits.PAYLOAD_MAX_BYTES`). The check runs in two phases: a fast-path `Content-Length` header check, then a streaming body read that aborts as soon as the limit is exceeded.

## Audit Events

All service account lifecycle and authentication events are captured in the immutable audit log, following the patterns established in [audit.md](audit.md).

### CRUD audit events

Service account CRUD operations emit standard resource audit events at `AuditLevel.META` (metadata only, no secret material).

### Authentication audit events

| Event | Source | Category | Severity | When |
|-------|--------|----------|----------|------|
| `LoginAttemptEvent` (success) | `src/syntara/auth/audit/login_attempt.py` | SECURITY_EVENT | INFO | Successful token issuance via client credentials grant |
| `LoginAttemptEvent` (failure) | `src/syntara/auth/audit/login_attempt.py` | SECURITY_EVENT | WARNING | Failed authentication (unknown client, bad secret, disabled SA) |

Login attempts include `method=LoginMethod.CLIENT_CREDENTIALS` and `principal_type=PrincipalType.SERVICE_ACCOUNT`. Error reasons include `UNKNOWN_USER`, `BAD_PASSWORD`, `DISABLED_SERVICE_ACCOUNT`, `DELETED_SERVICE_ACCOUNT`.

### Middleware rejection audit events

| Event | Source | Category | Severity | When |
|-------|--------|----------|----------|------|
| `DisabledSARejectionEvent` | `src/syntara/auth/audit/sa_rejection.py` | SECURITY_EVENT | WARNING | Request from deleted or disabled SA rejected by middleware |
| `StaleSATokenDetectionEvent` | `src/syntara/auth/audit/sa_rejection.py` | SECURITY_EVENT | INFO | Request with revoked (stale) SA token rejected by middleware |
| `DisabledSACredentialRejectionEvent` | `src/syntara/auth/audit/sa_rejection.py` | SECURITY_EVENT | WARNING | Request rejected because the SA credential is disabled or deleted |
| `ExpiredSACredentialRejectionEvent` | `src/syntara/auth/audit/sa_rejection.py` | SECURITY_EVENT | WARNING | Request rejected because the SA credential has expired |
| `MissingSACredentialClaimEvent` | `src/syntara/auth/audit/sa_rejection.py` | SECURITY_EVENT | WARNING | SA token rejected for missing the `cred_id` claim |

`DisabledSARejectionEvent` includes `is_alive` to distinguish deleted (`False`) from disabled (`True`). `StaleSATokenDetectionEvent` is throttled to at most one event per SA per 60 seconds to prevent audit log flooding. `DisabledSACredentialRejectionEvent` includes `credential_id` and `credential_status`. `ExpiredSACredentialRejectionEvent` includes `credential_id` and `expires_at`.

### Webhook auth audit events

| Event | Source | Category | Severity | When |
|-------|--------|----------|----------|------|
| `WebhookAuthSuccessEvent` | `src/syntara/workflows/audit/webhook_auth.py` | — | — | SA successfully authorized for a webhook/EDA trigger |
| `WebhookAuthFailureEvent` | `src/syntara/workflows/audit/webhook_auth.py` | — | — | SA authorization failed for a webhook/EDA trigger |

Both include `service_account_id`, `webhook_path`, `trigger_type`, and `workflow_id`.

### Audit actor context

The audit middleware (`src/syntara/audit/middleware.py`) detects `token_type == "service_account"` in JWT claims and sets `actor_type = PrincipalType.SERVICE_ACCOUNT` in the audit context.

## Telemetry

The API usage accumulator (`src/syntara/telemetry/api_usage_accumulator.py`) tracks requests by `principal_type`. Service account requests are recorded as `"service_account"`.

## Configuration

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `jwt_sa_access_token_lifetime_minutes` | int | 15 | SA access token lifetime (range: 1–60 minutes) |
| `service_accounts.credential_max_lifetime_days` | int | 180 | Caps how long credentials stay valid (0 = never expire, 1–730 days). Lives under the **Authentication** tab in the Settings UI — no restart required. |

## Error Handling

### Service account domain exceptions (`src/syntara/service_accounts/exceptions.py`)

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `ServiceAccountNotFoundError` | 404 | SA not found by ID |
| `ServiceAccountNameConflictError` | 409 | Duplicate name in project |
| `ServiceAccountCredentialNotFoundError` | 404 | Credential not found by ID |
| `ServiceAccountCredentialLimitError` | 409 | Exceeds 10 credentials per SA |
| `CredentialExpirationExceededError` | 400 | Expiration exceeds `sa_credential_max_lifetime_days` |
| `CredentialExpirationInPastError` | 400 | Expiration date is in the past |

### Auth exceptions

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `ServiceAccountWSTicketError` | 403 | SA token used for WebSocket ticket exchange |
| `AuthenticationRequiredError` | 401 | Invalid credentials at token endpoint |

### Webhook exceptions

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `WebhookAuthenticationRequiredError` | 401 | Missing/invalid SA Bearer token on webhook endpoint |
| `WebhookServiceAccountNotAuthorizedError` | 403 | SA not bound to the invoked trigger |
| `PayloadTooLargeError` | 413 | Webhook payload exceeds 1 MB |

## Implementation Status

| Component | Status |
|-----------|--------|
| ServiceAccount model + migration | Done |
| CRUD API + credential sub-resource | Done |
| Client credentials grant + token endpoint | Done |
| PrincipalType extension + RBAC | Done |
| Auth middleware integration (stale token, disabled/deleted SA) | Done |
| Secret rotation endpoint | Done |
| Token version mechanism | Done |
| Per-credential token revocation (`cred_id` claim) | Done |
| Hard-delete migration (removed soft-delete columns) | Done |
| Webhook/EDA trigger SA binding | Done |
| Webhook auth (Bearer token + per-trigger SA authorization) | Done |
| Audit events (auth, middleware rejection, webhook auth) | Done |
| Telemetry (API usage by principal type) | Done |
| Frontend UI (CRUD, credential management, webhook SA selector) | Done |
| Rate limiting | Not started |

## Key Files

| Path | Description |
|------|-------------|
| `src/syntara/service_accounts/models/service_account.py` | ServiceAccount SQLModel + ServiceAccountStatus enum |
| `src/syntara/service_accounts/models/service_account_credential.py` | ServiceAccountCredential SQLModel + enums |
| `src/syntara/service_accounts/schemas.py` | Service account API request/response schemas |
| `src/syntara/service_accounts/credential_schemas.py` | Credential API request/response schemas |
| `src/syntara/service_accounts/router.py` | Service account CRUD endpoints |
| `src/syntara/service_accounts/credential_router.py` | Credential CRUD endpoints (nested under service accounts) |
| `src/syntara/service_accounts/services/service_account_service.py` | Service account service layer (includes hard-delete logic) |
| `src/syntara/service_accounts/services/credential_service.py` | Credential service layer (generation, rotation, expiration enforcement) |
| `src/syntara/service_accounts/constants.py` | `MAX_CREDENTIALS_PER_SA` constant |
| `src/syntara/service_accounts/exceptions.py` | Domain exceptions |
| `src/syntara/service_accounts/error_handlers.py` | RFC 9457 error handlers |
| `src/syntara/auth/router.py` | Token endpoint (`POST /auth/token`) — client credentials grant |
| `src/syntara/auth/middleware.py` | StaleTokenMiddleware — disabled/deleted SA and stale token detection |
| `src/syntara/auth/services/token_service.py` | TokenService — SA-specific token creation (lifetime, claims) |
| `src/syntara/auth/dependencies.py` | `_user_from_payload()` — builds virtual principal for SA tokens |
| `src/syntara/auth/audit/sa_rejection.py` | DisabledSARejectionEvent, StaleSATokenDetectionEvent |
| `src/syntara/auth/audit/login_attempt.py` | LoginAttemptEvent with CLIENT_CREDENTIALS method |
| `src/syntara/auth/exceptions.py` | ServiceAccountWSTicketError |
| `src/syntara/auth/passwords.py` | Argon2id `hash_password` / `verify_password` (shared with user passwords) |
| `src/syntara/authz/models/assignments.py` | RoleAssignment with principal_id FK (supports SA) |
| `src/syntara/authz/resolver.py` | Policy resolution — generic via principal_id for users and SAs |
| `src/syntara/authz/services/role_assignment_service.py` | Role assignment CRUD — handles `"service_account"` principal type |
| `src/syntara/authz/role_conventions.py` | Builtin policies for `service_account` resource |
| `src/syntara/authz/role_assignment_router.py` | Role assignment API — `principal_type` includes `"service_account"` |
| `src/syntara/core/models/principal.py` | PrincipalType enum + `for_service_account()` factory |
| `src/syntara/workflows/webhook_router.py` | Webhook/EDA trigger endpoints with SA auth |
| `src/syntara/workflows/models/webhook_trigger_service_account.py` | Many-to-many trigger ↔ SA binding table |
| `src/syntara/workflows/services/webhook_trigger_service.py` | SA authorization verification and binding sync |
| `src/syntara/workflows/audit/webhook_auth.py` | WebhookAuthSuccessEvent, WebhookAuthFailureEvent |
| `src/syntara/workflows/exceptions.py` | WebhookAuthenticationRequiredError, WebhookServiceAccountNotAuthorizedError |
| `src/syntara/telemetry/api_usage_accumulator.py` | API usage tracking by principal_type |
| `src/syntara/core/config/base.py` | `jwt_sa_access_token_lifetime_minutes`, `sa_credential_max_lifetime_days` settings |
