# Access Control

This document defines how API endpoints are secured in Syntara and how the compliance test suite enforces coverage.

## Access Control Layers

Syntara uses three layers, each enforced via FastAPI dependency injection:

| Layer | Mechanism | What it does |
|-------|-----------|-------------|
| **Authentication** | `get_current_user` / `get_token_payload` | Validates the JWT and identifies the caller. Does NOT restrict access — any valid token passes. |
| **Authorization (RBAC)** | `PermissionChecker` | Checks whether the user has permission to perform a specific action on a specific resource (e.g. `workflow:create`). Delegates to the Rego evaluator. |
| **Visibility filtering** | `VisibilityFilter` / `ProjectScopeFilter` | Filters list query results to only resources the user is allowed to see. Also delegates to the Rego evaluator. |

### How to protect a route

Add RBAC as a route dependency or handler parameter:

```python
# Route-level dependency (most common for single-resource endpoints)
@router.post(
    "/credentials",
    dependencies=[Depends(PermissionChecker("credential", "create", body_project_field="project_id"))],
)
async def create_credential(...): ...

# Handler parameter (for list endpoints that need the filter result)
@router.get("/credentials")
async def list_credentials(
    visibility: Annotated[VisibilityResult, Depends(VisibilityFilter("credential", "read"))],
): ...
```

### What does NOT count as access control

- `get_current_user` alone — proves identity but does not gate permissions
- `NO_PERMISSION` sentinel — marks a route as deliberately unprotected for the route scanner, but does not enforce anything

## Compliance Test Suite

`tests/unit/api/test_auth_compliance.py` automatically discovers all registered API endpoints and validates each has an RBAC dependency (`PermissionChecker`, `VisibilityFilter`, or `ProjectScopeFilter`).

### How it works

1. Creates a lightweight FastAPI app with router discovery (no DB or Docker needed)
2. Iterates all `APIRoute` instances, skipping infrastructure paths (`/healthz/*`, `/metrics`, etc.)
3. Inspects each route's dependency tree for RBAC types
4. Routes without RBAC must be in one of two exclusion lists:
   - `AUTHENTICATED_EXCLUSIONS` — requires JWT, no RBAC (e.g. reference data catalogs, AAP proxy)
   - `PUBLIC_EXCLUSIONS` — no authentication at all (e.g. login, OIDC, webhooks)

### Tests

| Test | What it checks |
|------|---------------|
| `test_all_endpoints_have_rbac` | Every route has RBAC or is in an exclusion list |
| `test_authenticated_exclusions_actually_require_authn` | Routes in `AUTHENTICATED_EXCLUSIONS` actually require a JWT |
| `test_public_exclusions_are_actually_public` | Routes in `PUBLIC_EXCLUSIONS` do NOT require a JWT |
| `test_no_stale_exclusions` | No exclusion entries for routes that no longer exist or now have RBAC |

### Adding a new endpoint

1. Add `PermissionChecker` or `VisibilityFilter` — the test passes automatically
2. If RBAC is not applicable, add the route to `tests/unit/api/auth_exclusions.yml` under `authenticated` or `public` with a justification — this will be reviewed in the PR

### CI integration

The compliance tests run as part of `make test-unit` and `make test-coverage`. They are unit tests (no Docker/DB) and take ~0.1s.

## Key Source Files

| File | Role |
|------|------|
| `src/syntara/auth/dependencies.py` | `get_current_user`, `get_token_payload` — JWT validation |
| `src/syntara/authz/dependencies.py` | `PermissionChecker`, `VisibilityFilter`, `ProjectScopeFilter` — Rego-based RBAC |
| `src/syntara/core/syntara_router.py` | `NO_PERMISSION` sentinel, `SyntaraRouter` base class |
| `src/syntara/authz/resource_actions.py` | Route introspection helpers (`_iter_route_deps`, `_get_dep_instance`) |
| `tests/unit/api/test_auth_compliance.py` | Compliance test suite |
| `tests/unit/api/auth_exclusions.yml` | YAML-based exclusion registry (authenticated vs public) |
