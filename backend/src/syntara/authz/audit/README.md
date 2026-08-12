# Authorization Audit Events

Audit instrumentation for the authorization domain (`src/syntara/authz/`).

## Domain Events

### RoleAssignmentEvent

Tracks role assignment and revocation — the core "who gets what permissions" operation.

| Field | Type | Description |
|-------|------|-------------|
| `assignment_id` | UUID | Role assignment being acted on |
| `principal_type` | str | `"user"` or `"group"` |
| `principal_id` | UUID | User or group receiving/losing the role |
| `principal_name` | str | Display name of the principal |
| `role_name` | str | Name of the role being assigned/revoked |
| `action` | str | `"assigned"` or `"revoked"` |
| `project_id` | UUID \| None | Project scope (None for global assignments) |
| `error_type` | str \| None | Error class name if the operation failed |

**Handler:** `RoleAssignmentHandler`
- Category: `SECURITY_EVENT`
- Action: `role_assigned`, `role_revoked`
- Severity: `ERROR` on failure; `INFO` otherwise
- Sets `resource_urn` as `urn:syntara:role-assignment:{assignment_id}`

### RoleLifecycleEvent

Tracks role create, update, and delete operations. On delete, captures how many assignments were cascade-deleted.

| Field | Type | Description |
|-------|------|-------------|
| `role_id` | UUID | Role being acted on |
| `role_name` | str | Name of the role |
| `action` | str | `"created"`, `"updated"`, or `"deleted"` |
| `project_id` | UUID \| None | Owning project (None for system roles) |
| `affected_assignments_count` | int | Assignments cascade-deleted (populated on delete) |
| `error_type` | str \| None | Error class name if the operation failed |

**Handler:** `RoleLifecycleHandler`
- Category: `SECURITY_EVENT`
- Action: `role_created`, `role_updated`, `role_deleted`
- Severity: `WARNING` when deleting a role that has assignments; `ERROR` on failure; `INFO` otherwise
- Sets `resource_urn` as `urn:syntara:role:{role_id}`

### GroupMembershipEvent

Tracks adding and removing users from groups — membership grants inherited roles.

| Field | Type | Description |
|-------|------|-------------|
| `user_id` | UUID | User being added or removed |
| `username` | str | Display username of the user |
| `group_id` | UUID | Group being modified |
| `group_name` | str | Name of the group |
| `action` | str | `"added"` or `"removed"` |
| `error_type` | str \| None | Error class name if the operation failed |

**Handler:** `GroupMembershipHandler`
- Category: `SECURITY_EVENT`
- Action: `group_member_added`, `group_member_removed`
- Severity: `ERROR` on failure; `INFO` otherwise
- Sets `resource_urn` as `urn:syntara:group-membership:{group_id}:{user_id}`

**Emitted from:**
- Admin/API membership changes (`GroupsService`, `UsersService.create_user`)
- IdP group sync on OIDC login (`idp_group_sync._apply_group_membership_diff`)
- OIDC auto-created users (`_auto_create_user` → `authenticated` group)

Bulk membership diffs (admin `set_user_groups`, IdP sync) share
`dispatch_membership_diff_events` in this module.

Not covered: cascading membership cleanup when an identity provider is deleted (no domain event yet).

### PolicyLifecycleEvent

Tracks policy create, update, and delete operations. On delete, captures how many roles had the policy removed.

| Field | Type | Description |
|-------|------|-------------|
| `policy_id` | UUID | Policy being acted on |
| `policy_name` | str | Name of the policy |
| `action` | str | `"created"`, `"updated"`, or `"deleted"` |
| `project_id` | UUID \| None | Owning project (None for system policies) |
| `affected_roles_count` | int | Roles that referenced this policy (populated on delete) |
| `error_type` | str \| None | Error class name if the operation failed |

**Handler:** `PolicyLifecycleHandler`
- Category: `SECURITY_EVENT`
- Action: `policy_created`, `policy_updated`, `policy_deleted`
- Severity: `WARNING` when deleting a policy referenced by roles; `ERROR` on failure; `INFO` otherwise
- Sets `resource_urn` as `urn:syntara:policy:{policy_id}`

## Instrumentation Layers

| Layer | Status | Details |
|-------|--------|---------|
| 1. Middleware | Automatic | All authorization endpoints captured by `AuditMiddleware` |
| 2. `@audit` | Active | All 10 state-changing endpoints (policy/role/assignment CRUD) |
| 3. CRUD | Pending | Models inherit `BaseResource`, ready for AAP-73776 |
| 4. Domain Events | Active | `RoleAssignmentEvent`, `RoleLifecycleEvent`, `PolicyLifecycleEvent`, `GroupMembershipEvent` |

## Audit Trail Per Operation

**Group member add:** 3 events
1. `group_member_added` (GroupMembershipEvent, SECURITY_EVENT, INFO)
2. `group_member_add` (@audit decorator, SECURITY_EVENT; captures `group_id` + `request.user_id`)
3. `request_completed` (AuditMiddleware, 201)

**Group member remove:** 3 events
1. `group_member_removed` (GroupMembershipEvent, SECURITY_EVENT, INFO)
2. `group_member_remove` (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 204)

**User groups set (declarative replace):** 1 `@audit` + N domain events
1. One `group_member_added` / `group_member_removed` per membership diff (GroupMembershipEvent, SECURITY_EVENT)
2. `user_groups_set` (@audit decorator, SECURITY_EVENT; captures `user_id` + `request`)
3. `request_completed` (AuditMiddleware, 200)

**User create with initial groups:** N domain events (+ user_create `@audit`)
1. One `group_member_added` per initial membership including `authenticated` (GroupMembershipEvent, SECURITY_EVENT)
2. `user_create` (@audit decorator)
3. `request_completed` (AuditMiddleware, 201)

**OIDC auto-create user:** 1 domain event (no `@audit` on the helper)
1. `group_member_added` for the `authenticated` group (GroupMembershipEvent, SECURITY_EVENT)

**IdP group sync (OIDC login):** N domain events (no HTTP `@audit` on the sync helper)
1. One `group_member_added` / `group_member_removed` per session-scoped membership diff (GroupMembershipEvent, SECURITY_EVENT)

**Role assign:** 3 events
1. `role_assigned` (RoleAssignmentEvent, SECURITY_EVENT, INFO)
2. `create_role_assignment` (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 201)

**Role revoke:** 3 events
1. `role_revoked` (RoleAssignmentEvent, SECURITY_EVENT, INFO)
2. `delete_role_assignment` (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 204)

**Policy/role create or update:** 3 events
1. `policy_created`/`role_created`/etc. (domain event, SECURITY_EVENT, INFO)
2. `create_policy`/`create_role`/etc. (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 201 or 200)

**Role delete with cascading assignments:** 3 events
1. `role_deleted` (RoleLifecycleEvent, SECURITY_EVENT, WARNING, affected_assignments_count=N)
2. `delete_role` (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 204)

**Policy delete affecting roles:** 3 events
1. `policy_deleted` (PolicyLifecycleEvent, SECURITY_EVENT, WARNING, affected_roles_count=N)
2. `delete_policy` (@audit decorator, SECURITY_EVENT)
3. `request_completed` (AuditMiddleware, 204)
