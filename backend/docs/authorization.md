# Authorization

Syntara uses an in-process `regopy` evaluator for policy-based authorization. The system supports both Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC) with project-scoped multi-tenancy.

## Architecture

```
Request → Authentication → PermissionChecker → Policy Resolver → Rego Evaluator → Allow/Deny
```

1. **Authentication**: Identifies the user via `get_current_user()`
2. **PermissionChecker**: FastAPI dependency that extracts resource type, action, and project context from the request
3. **Policy Resolver**: Resolves the user's effective policies from role assignments and built-in role definitions (via roles, groups, and project assignments)
4. **Rego evaluator**: Evaluates the Rego policy against the resolved policies and request context
5. **Decision**: Allow (200) or deny (403 Forbidden)

Authorization is **deny-by-default** — requests are denied unless an explicit allow policy matches.

## Key Concepts

### Resource Types and Actions

Every authorization decision is about whether a user can perform an **action** on a **resource type**. The canonical catalog is built dynamically at startup by `build_resource_actions()` in `src/syntara/authz/resource_actions.py`, which introspects all registered route dependencies (`PermissionChecker`, `ProjectScopeFilter`) and merges them with `BUILTIN_POLICIES`. The `GET /authz/resource_actions` endpoint exposes the live catalog to API consumers.

#### Adding a New Resource Type or Action

1. Add a `PolicyInfo` to `BUILTIN_POLICIES` in `src/syntara/authz/role_conventions.py`
2. Use `PermissionChecker("resource", "action")` on the new endpoint

The registry is rebuilt automatically — no manual dictionary to maintain. Tests in `tests/unit/authz/test_resource_actions.py` validate that `PermissionChecker` calls, `BUILTIN_POLICIES`, and OpenAPI `x-app-permission` entries all stay in sync.

### Policies

A policy contains one or more **statements** that define what actions are allowed or denied:

```json
{
  "name": "workflow:read:any",
  "statements": [
    {
      "effect": "allow",
      "actions": ["workflow:read"],
      "scope": "any"
    }
  ]
}
```

- **effect**: `"allow"` or `"deny"`. Deny takes precedence over allow.
- **actions**: List of `"resource_type:action"` strings. Supports wildcards like `"workflow:*"`.
- **scope**: Controls where the policy applies:
  - `"any"` — applies globally to all resources
  - `"self"` — applies only to the user's own resources. Matches when `resource.id == user.id` (e.g., users) or when `resource.id` matches one of the user's group IDs (e.g., groups)
  - `"project"` — applies only within a specific project (set via project role assignments)

There are two categories of policies:

- **Built-in policies**: Defined in `BUILTIN_POLICIES` in `src/syntara/authz/role_conventions.py`. These exist only in code and are resolved at runtime — they are **not** stored in the database.
- **Custom policies**: Created via the API (system-level or project-scoped) and stored in the `policies` database table.

### Roles

A role bundles a set of policies. Like policies, roles come in two categories:

- **Built-in roles**: Defined in `BUILTIN_ROLES` in `src/syntara/authz/role_conventions.py`. Their policy assignments are declared via the `roles` tuple on each `PolicyInfo`. These are resolved at runtime and **not** stored in the database.
- **Custom roles**: Created via the API (system-level or project-scoped) and stored in the `roles` database table, with policies linked via `policy_names` or the `role_policies` join table.

### Groups

Groups organize users. The `authenticated` group implicitly includes all authenticated users. Users can be added to additional groups for fine-grained access.

### Projects

Projects provide resource isolation. Resources belong to projects, and users can have different roles in different projects.

## Built-in Roles

Defined in `BUILTIN_ROLES` in `src/syntara/authz/role_conventions.py`:

| Role | Builtin | Scope | Description | Key Permissions |
|------|---------|-------|-------------|-----------------|
| `admin` | yes | system | Full system access | All policies |
| `auditor` | yes | system | Read-only with audit visibility | Read workflows, executions, approvals, policies, roles, users, groups |
| `user` | yes | system | Base user permissions | Create projects, directory lookups (users/groups) |
| `project-admin` | yes | project | Full access within a project | Manage project, assign roles, CRUD workflows/executions, create custom roles/policies |
| `project-user` | yes | project | Standard access within a project | Read project, CRUD workflows, run executions |
| `project-auditor` | yes | project | Read-only within a project | Read project, workflows, executions, roles, policies |
| `authenticated` | no | system | Default permissions for all authenticated users | Read/update self, read own role assignments, manage own identity links |

## Database Schema

The authorization system uses these tables:

| Table | Model | Location | Description |
|-------|-------|----------|-------------|
| `policies` | `Policy` | `src/syntara/authz/models/policy.py` | Custom IAM-style policies with JSONB statements; optional `project_id` for project scoping |
| `roles` | `Role` | `src/syntara/authz/models/role.py` | Custom named roles; optional `project_id` for project scoping |
| `role_policies` | `RolePolicyLink` | `src/syntara/authz/models/role.py` | Many-to-many join table linking custom roles to custom policies |
| `principals` | `Principal` | `src/syntara/core/models/principal.py` | Supertype table for identity types that can own resources (users, future service accounts) |
| `groups` | `Group` | `src/syntara/core/models/group.py` | User groups with labels |
| `user_groups` | *(association table)* | `src/syntara/core/models/group.py` | User-to-group membership (SQLAlchemy Table) |
| `role_assignments` | `RoleAssignment` | `src/syntara/authz/models/assignments.py` | Principal-to-role with `principal_type` (user/group), `principal_id`, optional `project_id`; references roles by `role_name` (string) |
| `projects` | `Project` | `src/syntara/authz/models/project.py` | Resource isolation boundaries |

Built-in roles and policies are **not** stored in these tables. They live in `role_conventions.py` and are resolved at runtime by the policy resolver, then merged into API list/get responses by the service layer.

Role assignments reference roles by **name** (string), which allows a single assignment to refer to either a built-in role or a custom database role.

The `role_assignments` table uses a `principal_type` discriminator ('user' or 'group') and a **nullable `project_id`** column with conditional unique indexes to handle global and project-scoped assignments in a single table.

### Principals (Class-Table Inheritance)

The `principals` table is a supertype that provides unified identity attribution for entities that can own resources. Users (and future service accounts) have a row in `principals` whose `id` is shared with the entity's own primary key.

```
principals (id, principal_type)
    └── users.id        FK → principals.id   (principal_type = 'user')
```

Groups are **not** part of the class-table inheritance hierarchy. They use `RoleAssignment.principal_type` as a denormalized discriminator without FK integrity to the principals table.

This gives the database real referential integrity for resource ownership:

- **Resource ownership**: `UserOwnedResource.created_by` and `updated_by` FK to `principals.id` (previously `users.id`), so future service accounts can also own resources.

**Creating users and service accounts** works via normal `session.add()` — a `before_flush` event listener automatically inserts the corresponding `Principal` row before SQLAlchemy flushes the entity. No special helper is needed.

**Deletion**: if hard-delete is ever implemented, the `Principal` row must be handled first — `created_by`/`updated_by` FKs will block deletion of any principal still referenced by resources.

## How Roles Are Assigned

Roles reach users through multiple paths:

```
User
├── Direct: RoleAssignment (principal_type=user, project_id=NULL) → Role → Policies (global scope)
├── Direct: RoleAssignment (principal_type=user, project_id=X)    → Role → Policies (project scope)
├── Groups:
│   └── GroupMembership → Group → RoleAssignment (principal_type=group, project_id=NULL) → Role → Policies (global)
│   └── GroupMembership → Group → RoleAssignment (principal_type=group, project_id=X)    → Role → Policies (project)
```

`RoleAssignment` uses a nullable `project_id` column to distinguish scope:

- **`project_id IS NULL`** → global assignment, policies apply system-wide
- **`project_id IS NOT NULL`** → project-scoped assignment, policies apply only within that project

## Default Bootstrap State

On first boot, the seed module (`src/syntara/authz/seed.py`) creates:

- `authenticated` group (builtin, implicit — all users belong to it)
- `admins` group (builtin)
- `auditors` group (builtin)
- `users` group (builtin — local users are added on creation by default)
- `default` project
- `admin` user (member of `admins` and `users` groups)
- `system` user (member of `admins` and `users` groups)
- `authenticated` role → `authenticated` group via `RoleAssignment` (principal_type=group, project_id=NULL, global, **builtin**)
- `user` role → `users` group via `RoleAssignment` (principal_type=group, project_id=NULL, global, **builtin**)
- `admin` role → `admins` group via `RoleAssignment` (principal_type=group, project_id=NULL, global, **builtin**)
- `auditor` role → `auditors` group via `RoleAssignment` (principal_type=group, project_id=NULL, global, **builtin**)
- `project-user` role → `users` group via `RoleAssignment` (principal_type=group, project_id=default project, project-scoped, revocable)

The `authenticated`, `user`, `admin`, and `auditor` role assignments are marked `is_builtin=True` and cannot be revoked via the API. The `project-user` assignment on the `users` group is revocable, allowing admins to customise default project permissions.

New local users are automatically added to the `users` group by default. The API accepts an optional `group_names` field on user creation: omit it to use the default, pass an empty list to skip group assignment, or pass specific group names to override.

There are two seeding paths:
- `seed_authz_data()` — full seed used by tests after table truncation.
- `seed_groups_project_admin()` — lightweight seed that creates groups, project, admin user, and role assignments. Used at app startup after migrations have already run.

Both functions only create groups, the default project, the admin user, and role assignments. Built-in policies and roles are not seeded into the database — they are resolved from `role_conventions.py` at runtime.

## Protecting API Endpoints

Use the `PermissionChecker` dependency on your router endpoints:

```python
from syntara.authz.dependencies import PermissionChecker

# Simple check: user must have workflow:create permission
@router.post("", dependencies=[Depends(PermissionChecker("workflow", "create"))])
async def create_workflow(...):
    ...

# Project-scoped check: resolves project from path parameter
@router.put(
    "/{project_id}",
    dependencies=[Depends(PermissionChecker(
        "project", "update",
        project_param="project_id",
    ))]
)
async def update_project(...):
    ...

# Resource lookup: resolves project from the resource's project_id field
@router.delete(
    "/{workflow_id}",
    dependencies=[Depends(PermissionChecker(
        "workflow", "delete",
        resource_model=Workflow,
        resource_id_param="workflow_id",
    ))]
)
async def delete_workflow(...):
    ...

# Body-based: extracts project_id from the request body
@router.post(
    "",
    dependencies=[Depends(PermissionChecker(
        "workflow", "create",
        body_project_field="project_id",
    ))]
)
async def create_workflow_in_project(...):
    ...
```

`PermissionChecker` parameters:

| Parameter | Description |
|-----------|-------------|
| `resource_type` | The resource type (e.g., `"workflow"`, `"project"`) |
| `action` | The action (e.g., `"read"`, `"create"`, `"delete"`) |
| `project_param` | Path parameter name for project-scoped checks (looks up project name by UUID) |
| `resource_model` | SQLModel class with a `project_id` field (used with `resource_id_param`) |
| `resource_id_param` | Path parameter name for the resource ID (used with `resource_model`) |
| `body_project_field` | JSON body field name containing a project UUID |

### Filtering List Endpoints with VisibilityFilter

Use `VisibilityFilter` to restrict list queries based on the user's effective policies. It resolves project-scoped access, self-scope access, and unrestricted access in a single policy evaluation:

```python
from syntara.authz.dependencies import VisibilityFilter
from syntara.authz.engine import VisibilityResult

# Project-scoped resources (workflows, executions, approvals, credentials, projects)
@router.get("")
async def list_workflows(
    visibility: VisibilityResult = Depends(VisibilityFilter("workflow", "read")),
):
    # Convert to AllowedProjectsResult for project-scoped filtering
    allowed_projects = visibility.to_allowed_projects()
    ...

# System-scoped resources (users, groups — admin/auditor only)
@router.get("")
async def list_users(
    visibility: VisibilityResult = Depends(VisibilityFilter("user", "read")),
):
    # Convert to ID restriction — None means unrestricted, [] means no access
    id_restriction = visibility.to_id_restriction()
    ...

# Groups use group membership IDs instead of user ID (admin/auditor only)
@router.get("")
async def list_groups(
    visibility: VisibilityResult = Depends(VisibilityFilter("group", "read")),
):
    id_restriction = visibility.to_id_restriction(use_group_ids=True)
    ...
```

`VisibilityResult` fields:

| Field | Type | Description |
|-------|------|-------------|
| `unrestricted` | `bool` | User has `any`-scope access — no filtering needed |
| `allowed_project_ids` | `list[UUID]` | Projects the user can access via `project`-scope policies |
| `has_self_scope` | `bool` | User has `self`-scope access to their own resources |
| `self_user_id` | `UUID \| None` | The user's own ID (set when `has_self_scope` is True) |
| `self_group_ids` | `list[UUID]` | IDs of groups the user belongs to (set when `has_self_scope` is True) |

`VisibilityResult` methods:

| Method | Returns | Use Case |
|--------|---------|----------|
| `to_allowed_projects()` | `AllowedProjectsResult` | Project-scoped resources (workflows, executions, etc.) |
| `to_id_restriction()` | `list[UUID] \| None` | System-scoped resources filtered by user ID (users) |
| `to_id_restriction(use_group_ids=True)` | `list[UUID] \| None` | System-scoped resources filtered by group membership (groups) |

> **Note:** `ProjectScopeFilter` still exists for backward compatibility but new endpoints should use `VisibilityFilter`.

## Conditions (ABAC)

Policies support optional conditions for attribute-based matching. All specified conditions must match (AND logic):

```json
{
  "name": "workflow:read:dev-only",
  "statements": [
    {
      "effect": "allow",
      "actions": ["workflow:read"],
      "scope": "any",
      "conditions": {
        "resource_labels": {"env": "dev"},
        "resource_labels_not": {"env": "prod"},
        "user_labels": {"team": "platform"},
        "user_metadata": {"clearance": "high"},
        "group_labels": {"department": "engineering"}
      }
    }
  ]
}
```

| Condition | Matches Against |
|-----------|----------------|
| `resource_labels` | Labels on the resource being accessed |
| `resource_labels_not` | Inverted — resource must NOT have these label values |
| `user_labels` | Labels on the requesting user |
| `user_metadata` | Metadata on the requesting user |
| `resource_metadata` | Metadata on the resource |
| `group_labels` | Labels on any group the user belongs to |

If a condition key is absent from the policy, it is not checked (backward compatible).

## Policy Logic

The Rego policy (`src/syntara/authz/rego/authz.rego`) implements deny-first evaluation:

1. **Deny check**: If any policy with `effect: "deny"` matches the action, scope, and conditions → **denied**
2. **Allow check**: If no deny matched AND any policy with `effect: "allow"` matches → **allowed**
3. **Default**: If neither matched → **denied** (deny-by-default)

The evaluator response includes:
- `allow` / `deny` — boolean decision
- `matched_policy` — name of the first allow policy that matched
- `denied_by` — name of the first deny policy that fired
- `denial_reason` — `"policy_deny"` if explicitly denied
- `allowed_projects` — set of project names the user can access (for list filtering)

## Query Endpoints

The `/authz` router provides introspection endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/authz/can_i` | POST | Check if current user can perform an action |
| `/authz/who_can` | POST | List users who can perform an action (requires `authz:query`) |
| `/authz/what_can_i` | POST | List all permissions for the current user |
| `/authz/resource_actions` | GET | List all available resource types and their valid actions |

`GET /authz/resource_actions` returns the full catalog of resource types and actions as a map. It requires authentication but no specific permission, and involves no database query — the data is static.

## Unified Role Assignment Endpoints

The `/role_assignments` endpoints provide a unified view of both user and group role assignments.

```
POST   /role_assignments           — create (global or project-scoped)
GET    /role_assignments           — list with project-aware visibility
GET    /role_assignments/{id}      — detail with project-aware visibility
DELETE /role_assignments/{id}      — revoke
```

**Query parameters (list):**

| Parameter | Description |
|-----------|-------------|
| `principal_type` | Filter by `user` or `group` |
| `principal_name` | Filter by username or group name |
| `role_name` | Filter by role name |
| `project_id` | Filter by project ID |
| `sort` | Sort field (prefix with `-` for descending). Sortable: `created_at`, `principal_name`, `principal_type`, `role_name`, `project_name` |
| `cursor` | Cursor for pagination |
| `limit` | Page size |
| `include_total` | Include total count |

**Visibility:** Driven by `VisibilityFilter("role-assignment", "read")`. Users with `any`-scope see all. Users with `project`-scope see assignments in their authorized projects. Users with `self`-scope see only their own (direct and via groups).

## Project Admin Endpoints

Projects expose convenience endpoints for managing role assignments, custom roles, and custom policies within the project scope. All are under `/projects/{project_id}/...`.

### Role Assignments

| Endpoint | Permission | Description |
|----------|------------|-------------|
| `POST /{project_id}/role_assignments` | `role-assignment:assign` | Assign a role to a user or group within the project |
| `GET /{project_id}/role_assignments` | *(visibility-based)* | List role assignments for the project |
| `DELETE /{project_id}/role_assignments/{id}` | `role-assignment:revoke` | Remove a role assignment |

For visibility-based endpoints: admin/auditor/project-admin see all assignments; other users see only their own.

### Custom Project Roles

| Endpoint | Permission | Description |
|----------|------------|-------------|
| `POST /{project_id}/roles` | `role:create` | Create a custom role scoped to this project |
| `GET /{project_id}/roles` | `role:read` | List project-owned and global project-scoped roles |
| `GET /{project_id}/roles/{role_id}` | `role:read` | Get a role's details |
| `PATCH /{project_id}/roles/{role_id}` | `role:update` | Update a project role |
| `DELETE /{project_id}/roles/{role_id}` | `role:delete` | Delete a project role |

### Custom Project Policies

| Endpoint | Permission | Description |
|----------|------------|-------------|
| `POST /{project_id}/policies` | `policy:create` | Create a custom policy scoped to this project |
| `GET /{project_id}/policies` | `policy:read` | List project-owned and global project-scoped policies |
| `GET /{project_id}/policies/{policy_id}` | `policy:read` | Get a policy's details |
| `PATCH /{project_id}/policies/{policy_id}` | `policy:update` | Update a project policy |
| `DELETE /{project_id}/policies/{policy_id}` | `policy:delete` | Delete a project policy |

### Project Creation

When a project is created, the creator is automatically assigned the `project-admin` role for that project.

### Sub-resources

Projects also expose filtered views of their resources:

| Endpoint | Permission | Description |
|----------|------------|-------------|
| `GET /{project_id}/workflows` | `workflow:read` | List workflows in the project |
| `GET /{project_id}/approvals` | `approval:read` | List approvals in the project |
| `POST /{project_id}/credentials` | `credential:create` | Create a credential in the project |
| `GET /{project_id}/credentials` | `credential:read` | List credentials in the project |
| `GET /{project_id}/credentials/{id}` | `credential:read` | Get a credential (secrets masked) |
| `PATCH /{project_id}/credentials/{id}` | `credential:update` | Update a credential in the project |
| `DELETE /{project_id}/credentials/{id}` | `credential:delete` | Delete a credential from the project |
| `GET /{project_id}/credentials/{id}/workflows` | `credential:read` | List workflows referencing a credential |

## User and Group Access Model

Full user and group endpoints (`/users`, `/groups`) require the `user:read` or `group:read` permission, which is granted only to the `admin` and `auditor` roles. Regular users can read their own record via `self`-scope (granted by the `authenticated` role).

For non-admin users who need to look up users or groups (e.g., to populate assignment dropdowns), lightweight **directory endpoints** are available:

| Endpoint | Permission | Returns |
|----------|------------|---------|
| `GET /users_directory` | `user-directory:read` | `id` + `username` only |
| `GET /groups_directory` | `group-directory:read` | `id` + `name` only |

The `user-directory:read` and `group-directory:read` policies are granted to the `user` role, so all standard users can perform directory lookups. These endpoints support cursor pagination, sorting, and filtering (by `username` or `name` respectively) but expose no sensitive fields.

## Policy and Role Management

Built-in policies and roles are defined as static registries in `src/syntara/authz/role_conventions.py`. They are the single source of truth and are resolved at runtime — they are never stored in or read from the database.

### `PolicyInfo` — Built-in Policy Definition

Each `PolicyInfo` declares a resource, action, scope, and which built-in roles receive the policy:

```python
PolicyInfo("workflow", "create", scope="project", roles=("project-admin", "project-user"))
```

This generates a policy named `workflow:create:project` and assigns it to the `project-admin` and `project-user` roles.

### `RoleInfo` — Built-in Role Definition

Each `RoleInfo` declares a role name, description, and scope:

```python
RoleInfo("project-admin", "Full access to a project", scope="project")
```

The role's policies are derived by inverting the `roles` tuples across all `PolicyInfo` entries.

### Adding a New Built-in Policy

Add a `PolicyInfo` entry to `BUILTIN_POLICIES` in `role_conventions.py`:

```python
BUILTIN_POLICIES: list[PolicyInfo] = [
    ...
    PolicyInfo("credential", "archive", roles=("admin", "project-admin")),
]
```

No migration is needed — the policy is resolved at runtime. The sync tests will fail if the `resource:action` pair is not registered.

### Adding a New Built-in Role

Add a `RoleInfo` to `BUILTIN_ROLES` and assign policies via the `roles` tuple on existing or new `PolicyInfo` entries:

```python
BUILTIN_ROLES: list[RoleInfo] = [
    ...
    RoleInfo("credential-manager", "Manages credentials across projects"),
]

# Then add roles=("credential-manager",) to relevant PolicyInfo entries
```

### Custom Roles and Policies

Custom roles and policies are created via the API and stored in the database. They can be scoped to a project (via `project_id`) or be system-wide.

- **System-level**: Created via `/roles` and `/policies` endpoints (admin only)
- **Project-level**: Created via `/projects/{id}/roles` and `/projects/{id}/policies` endpoints (project-admin)

**Scope matching**: Roles can only reference policies from the same scope. Project-scoped roles can only include policies from the same project. System-scoped roles can only include global policies. Cross-project or cross-scope policy assignments are rejected at creation and update time.

## CLI Tools

The `tools/authz_cli.py` script provides commands for managing authorization data during development:

```bash
# Seed built-in data
uv run tools/authz_cli.py seed-builtin

# User management (authenticates as admin by default)
uv run tools/authz_cli.py create-user alice --email alice@test.com --full-name "Alice" --password secret
uv run tools/authz_cli.py list-users

# Group management
uv run tools/authz_cli.py create-group platform-team
uv run tools/authz_cli.py add-group-member platform-team alice

# Role assignment (global)
uv run tools/authz_cli.py assign-role user --user alice           # direct user→role
uv run tools/authz_cli.py assign-role user --group platform-team  # group→role

# Role assignment (project-scoped)
uv run tools/authz_cli.py assign-role project-admin --user bob --project staging

# Project management (as a specific user)
uv run tools/authz_cli.py --username alice --password secret create-project staging

# Permission checks (as a specific user)
uv run tools/authz_cli.py --username alice --password secret can-i read workflow wf-1
uv run tools/authz_cli.py --username alice --password secret what-can-i
```

## Local Development Setup

Authorization is evaluated in-process, so local development does not require a separate policy sidecar:

```bash
# Start all services
make run-all
```

The evaluator loads Rego policies from `src/syntara/authz/rego/`.

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `APP_AUTHZ_DEFAULT_PROJECT` | `default` | Default project name |

## Testing

```bash
# Run all authz tests
make test-all

# Unit tests (Rego policy logic via regopy)
uv run pytest tests/unit/authz/ -v

# Integration tests (API-level authz enforcement)
uv run pytest tests/integration/api/test_authz*.py -v
```

Unit tests validate the Rego policy directly using the `regopy` evaluator. Integration tests exercise the full stack with mocked evaluator dependencies where appropriate.
