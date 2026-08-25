# Permission Gating and RBAC

This document covers the frontend permission gating architecture — from API calls through hooks, components, navigation, and testing.

## API Layer

Two authorization endpoints, accessed via `accessFetchClient` in `routes/access/accessClient.ts`:

| Endpoint                 | Purpose                                                                 | Used by                                           |
| ------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------- |
| `POST /authz/can_i`      | Single permission check; optional `check_any_project` for hub/nav gates | `useCanI`, `usePermissionAnywhere`, nav filtering |
| `POST /authz/what_can_i` | Bulk permission list (all allowed actions / project names)              | `useApprovalDecideProjects`, enumerating projects |

## Core Hooks

### `useCanI(action, resourceType, options?)` — `hooks/useCanI.ts`

Single permission check via TanStack Query. Returns `{ allowed, isChecking, isError }`.

- **Safe-false default**: returns `allowed: false` until the check resolves or on error — gated UI stays disabled until confirmed.
- **Caching**: `staleTime: Infinity`, `retry: false`. Queries are deduplicated by `queryKey: ['authz', 'can_i', body]`.
- **Options**: `resourceId`, `resourceProject`, `checkAnyProject` (maps to `check_any_project` on the API), `enabled`. Prefer a concrete `resourceProject` when the page already has project context (e.g. workflow builder).
- **Invalidation**: after role/assignment mutations, call `invalidateAuthzCaches(queryClient)` (invalidates both `['authz', 'can_i']` and `['all-permissions']`).
- **Logout**: `queryClient.clear()` in `useAuthStore` wipes all cached permissions.

### `usePermissionChecks(permissions, options?)` — `hooks/usePermissionChecks.ts`

Batch permission checks for navigation filtering. Takes an array of `{ action, resourceType }` and returns a `Record<'resourceType:action', boolean>` using OR logic. Pass `{ checkAnyProject: true }` so project-scoped grants count (used by `useFilteredNavigationItems`).

### `usePermissionAnywhere(action, resourceType)` — `hooks/usePermissionAnywhere.ts`

Thin wrapper around `useCanI(..., { checkAnyProject: true })`. True when the user has the permission at system scope **or** in any project. Used for hub/nav visibility that must work for project-admins without a selected project.

Prefer plain `useCanI` with a concrete `resourceProject` when the page already has project context (row actions, detail pages, credentials). Do **not** use `check_any_project` for update/delete/rotate UI, and do **not** send `check_any_project` together with `resource_project` (API rejects the mix). Empty `resource_project` alone is never a wildcard.

### Access Management hub gating

`useAccessManagementPermissions` uses `check_any_project` for project/assignments/SA tab visibility, but **hub access** (`canAccessPage`) only ORs admin-worthy grants (`user`/`group`/`role-assignment`/`system service_account`/`role`/`policy`/`token revocation`). Project-only `project:read` or `service_account:read` must not open the hub (shared with project-user / project-auditor). Global Roles/Policies tabs require system-scoped `role:read` / `policy:read` only.

### `permissionTooltip(actionDescription, policyName)` — `hooks/permissionUtils.ts`

Generates standard tooltip copy for disabled actions:

> "To {actionDescription}, you need a role with the {policyName} policy. Contact your Admin to request access."

## Domain Hooks

Each page area has a dedicated `use*Permissions` hook that aggregates multiple `useCanI` calls and provides `tooltips` for disabled actions.

| Hook                             | File                                                                        | Permissions checked                                                                                                       |
| -------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `useWorkflowPermissions`         | `routes/workflows/useWorkflowPermissions.ts`                                | create via `check_any_project` when no project selected; update/delete/run use `resourceProject` or system-scoped `can_i` |
| `useCredentialPermissions`       | `routes/configuration/credentials/useCredentialPermissions.ts`              | `credential:create`, `credential:update`, `credential:delete`                                                             |
| `useBuilderPermissions`          | `routes/builder/useBuilderPermissions.ts`                                   | create/update/delete/run with `resourceProject`; new workflows use `check_any_project` for create                         |
| `useCredentialDetailPermissions` | `routes/configuration/credentials/useCredentialDetailPermissions.ts`        | `workflow:read`                                                                                                           |
| `useSettingsPermissions`         | `routes/configuration/settings/useSettingsPermissions.ts`                   | `setting:read`, `setting:write`                                                                                           |
| `useAccessManagementPermissions` | `routes/access-management/useAccessManagementPermissions.ts`                | Hub + tabs: `can_i` (+ `check_any_project` for project/assignments/SA); Roles/Policies system-only                        |
| `useUserPermissions`             | `routes/access-management/useUserPermissions.ts`                            | `user:create`, `user:update`, `user:delete`, `admin:revocation:execute`                                                   |
| `useGroupPermissions`            | `routes/access-management/useGroupPermissions.ts`                           | `group:create`, `group:update`, `group:delete`, `group:manage-members`                                                    |
| `useProjectPermissions`          | `routes/access-management/useProjectPermissions.ts`                         | `project:create` (hub); update/delete require concrete `resourceProject` per row                                          |
| `useServiceAccountPermissions`   | `routes/access-management/service-accounts/useServiceAccountPermissions.ts` | create via `check_any_project` on hub; update/delete/rotate require concrete `resourceProject`                            |
| `useRolePermissions`             | `routes/access/useRolePermissions.ts`                                       | `role:create`, `role:update`, `role:delete`                                                                               |
| `useAssignmentPermissions`       | `routes/access/useAssignmentPermissions.ts`                                 | `role-assignment:assign`, `role-assignment:revoke`                                                                        |
| `useIdentityProviderPermissions` | `routes/access-management/authentication/useIdentityProviderPermissions.ts` | `identity-provider:create/update/delete/test`, `admin:revocation:execute`                                                 |
| `useUserIdentityPermissions`     | `routes/access-management/users/useUserIdentityPermissions.ts`              | `user_identity:attach`, `user_identity:detach`                                                                            |
| `useUserDetailPermissions`       | `routes/access-management/users/useUserDetailPermissions.ts`                | `user:read`, `group:read`, `user_identity:read`, `role-assignment:read`                                                   |
| `useGroupDetailPermissions`      | `routes/access-management/groups/useGroupDetailPermissions.ts`              | `group:read`, `role-assignment:read`                                                                                      |
| `useProjectDetailPermissions`    | `routes/access-management/projects/useProjectDetailPermissions.ts`          | `role-assignment:read`                                                                                                    |
| `useApprovalPermissions`         | `routes/approvals/useApprovalPermissions.ts`                                | `approval:read`, `approval:decide`                                                                                        |
| `useApprovalDecideProjects`      | `routes/approvals/useApprovalDecideProjects.ts`                             | `approval:decide` (via `what_can_i`, project-scoped)                                                                      |
| `useCanDecideApproval`           | `routes/approvals/useCanDecideApproval.ts`                                  | Checks if user can decide specific approval (approver list + group membership)                                            |
| `useApprovalDecideUsers`         | `routes/builder/node-forms/useApprovalDecideUsers.ts`                       | `approval:decide` (via `who_can`, all authorized users)                                                                   |
| `useApprovalDecideGroups`        | `routes/builder/node-forms/useApprovalDecideGroups.ts`                      | All groups (MVP: no filtering, see hook docs for limitations)                                                             |

## UI Gating Components

### `DisabledWithTooltip` — `components/DisabledWithTooltip.tsx`

Wraps an action button/control. When `isDisabled` is true, renders a PF `Tooltip` around the child. Pair with `isAriaDisabled` on the button itself.

```tsx
<DisabledWithTooltip isDisabled={!permissions.canCreate} content={permissions.tooltips.create}>
  <Button isAriaDisabled={!permissions.canCreate} onClick={permissions.canCreate ? handleCreate : undefined}>
    Create
  </Button>
</DisabledWithTooltip>
```

### `ProtectedRoute` — `components/ProtectedRoute.tsx`

Route guard that checks a single permission via `useCanI`. Shows a spinner while checking, `SynEmptyStateAccessDenied` when denied, and renders children when allowed. Used for create/edit routes.

### `SynEmptyStateAccessDenied` — `components/states/SynEmptyStateAccessDenied.tsx`

Page-level access denied state. Two usage patterns:

1. **Via `ProtectedRoute`** — for create/edit routes, set `routePermission` in `navigationItems.tsx` and `ProtectedRoute` handles the rest.
2. **Inline in page components** — for pages that need custom loading/layout around the access-denied state (e.g. `AccessManagement.tsx`, `Authentication.tsx`, `Settings.tsx`, `EditGroupMapping.tsx`). Check permissions with `useCanI` and render `SynEmptyStateAccessDenied` directly when denied.

Prefer `ProtectedRoute` (pattern 1) for simple route guards. Use inline rendering (pattern 2) when the page has surrounding chrome (breadcrumbs, tabs, layout) that should still render around the access-denied state.

### `PermissionGate` — `components/PermissionGate.tsx`

Declarative wrapper around `useCanI`. Currently used only in tests — not in production code.

## Navigation Filtering

Navigation items are filtered based on permissions via `useFilteredNavigationItems` + `usePermissionChecks`.

### `requiredPermissions` (array, OR logic)

Set on `TNavigationItem` in `navigationItems.tsx`. The nav item is visible if the user has ANY of the listed permissions.

```tsx
{
  label: 'Settings',
  path: AppRoute.Settings,
  requiredPermissions: [{ action: 'read', resourceType: 'setting' }],
}
```

### `routePermission` (single, route guard)

Set on `TNavigationItem` for create/edit routes. Wraps the route component in `ProtectedRoute`, blocking access with `SynEmptyStateAccessDenied` if the permission check fails.

```tsx
{
  label: 'Create User',
  path: AppRoute.AccessManagement.CreateUser,
  routePermission: { action: 'create', resourceType: 'user' },
}
```

## Three-Tier UX Model

| Permission level       | Navigation                       | Page content                              | Actions                                                       |
| ---------------------- | -------------------------------- | ----------------------------------------- | ------------------------------------------------------------- |
| **No read permission** | Hidden via `requiredPermissions` | `SynEmptyStateAccessDenied` on direct URL | None                                                          |
| **Read only**          | Visible                          | Controls rendered read-only               | Action buttons disabled with tooltips (`DisabledWithTooltip`) |
| **Read + write**       | Visible                          | All controls editable                     | Full CRUD                                                     |

**When to hide vs disable**: Disable action buttons with tooltips in list/detail views so users know the action exists but is restricted. Hide Save/Reset buttons entirely in settings-style forms where read-only mode is the norm.

## Tab-Level Gating

Detail pages and top-level pages with multiple tabs conditionally show/hide tabs based on permissions. This is a distinct pattern between nav-level and action-level gating.

### Top-level tabs (`useAccessManagementPermissions`)

`AccessManagement.tsx` uses `useAccessManagementPermissions` to filter which tabs are visible (Users, Groups, Projects, Assignments, Service Accounts, Roles, Policies, Check access, Token Revocation).

**Access Management hub visibility (AAP-83294):**

- Nav `requiredPermissions` are admin-worthy only: `user:read`, `group:read`, `role-assignment:read`, `role-assignment:assign` (OR). Do **not** use `project:read` or `service_account:read` alone — those are shared with project-user / project-auditor.
- Page access (`canAccessPage`) follows the same idea: project-scoped `role-assignment:read|assign` (via `what_can_i`) unlocks the hub; project-scoped `project:read` / `service_account:read` alone does not.
- Global **Roles** / **Policies** tabs require system-scoped `role:read` / `policy:read` (unscoped `can_i` only) so project-admins are not shown the system inventory.
- Project-admins typically see Assignments, Projects, and Service Accounts tabs.
- Project role **create** from project context uses `AddRoleDialog` / `AddProjectRoleDialog` against `POST /projects/{id}/roles`. Project role edit/delete and a dedicated project-roles tab are not wired yet; global Roles hub remains system-scoped.

### Detail-page tabs (`use*DetailPermissions`)

`useUserDetailPermissions`, `useGroupDetailPermissions`, and `useProjectDetailPermissions` control which tabs appear on detail pages. For example, on a user detail page, the Groups, Identities, and Assignments tabs are only shown if the user has the corresponding `read` permission.

```tsx
const { canReadGroups, canReadIdentities, canReadAssignments } = useUserDetailPermissions(userId)
const visibleTabs = computeVisibleTabs(canReadGroups, canReadIdentities, canReadAssignments, isLoading)
```

### Self-permission exception

`useUserDetailPermissions` has a special case: when a user views their **own** profile, the Groups, Identities, and Assignments tabs are always visible — even without system-wide read permission for those resources. This is implemented via an `isSelf` check that compares the viewed user ID against the authenticated user's ID from `/auth/me`.

```tsx
const isSelf = !!viewedUserId && !!currentUserId && viewedUserId === currentUserId
return {
  canReadGroups: canReadGroups || isSelf,
  canReadIdentities: canReadIdentitiesGlobal || isSelf,
  canReadAssignments: canReadAssignmentsGlobal || isSelf,
}
```

When adding new detail-page tabs with permission gating, consider whether a self-permission exception is appropriate.

## Builder Read-Only Mode

The workflow builder uses a unique gating pattern: instead of hiding or disabling individual actions, the entire editor enters **read-only mode** when the user lacks edit permissions.

`useBuilderPermissions(isNew, isBuiltin?, projectId?)` returns `canEdit`, which maps to either `workflow:create` (new workflow) or `workflow:update` (existing workflow) depending on the `isNew` flag. Pass the workflow's `projectId` (or the selected project when creating) as `resourceProject` so project-scoped grants are evaluated. For new workflows before a project is selected, create uses `check_any_project` so project-user/project-admin can edit immediately; update/delete/run still require a concrete project. The safe-false default means the builder starts read-only until permissions confirm edit access.

When `canEdit` is false, the builder:

- Disables the canvas (no adding/moving/deleting nodes)
- Disables Save, Publish/Unpublish buttons with tooltips
- Disables the workflow name input
- Run and Delete buttons are gated independently via `canRun` and `canDelete`

This is the correct pattern for editor-style pages where many controls are affected by a single permission. Use inline `DisabledWithTooltip` for pages with a small number of independent actions.

## Cache Behavior

- `staleTime: Infinity` on all `useCanI` queries — permissions are fetched once per session.
- `queryClient.clear()` on logout wipes all cached permissions (via `useAuthStore`).
- After role or assignment mutations: call `invalidateAuthzCaches(queryClient)` from
  `packages/syntara-ui/src/hooks/invalidateAuthzCaches.ts` (invalidates `['authz', 'can_i']`
  and `['all-permissions']`).

**Trade-off**: `staleTime: Infinity` means permissions revoked server-side won't take effect in a user's browser until cache invalidation or logout. This is intentional — permission checks are high-frequency and low-change, so we trade freshness for reduced API load. Server-side enforcement remains the ultimate authority; the UI cache is a UX optimization, not a security boundary.

## Mock API Roles

The mock API in `packages/syntara-mock-api/src/handlers.ts` defines four roles via the `POST /authz/can_i` handler. The username is extracted from the Bearer token (`mock-token-{username}`).

| Role                | Behavior                                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **admin** (default) | All actions on all resource types allowed                                                                                     |
| **viewer**          | Read-only on `workflow`, `execution`, `approval`, `credential`, `integration`; all else denied                                |
| **user**            | Read-only on `workflow`, `execution`, `approval`, `credential`, `user`, `group`, `role`, `policy`, `authz`; all writes denied |
| **auditor**         | All writes denied; `user_identity` denied entirely; otherwise read allowed                                                    |

Write actions: `create`, `update`, `delete`, `write`, `assign`, `revoke`, `execute`, `manage-members`, `attach`, `detach`, `test`, `run`, `decide`.

### Adding new permissions to the mock API

1. Add the resource type to the appropriate role blocks in the `can_i` handler.
2. Add E2E test coverage for the new gating in `e2e/permission-gating.spec.ts`.
3. Use `viewerApp`, `auditorApp`, `userApp` fixtures for role-specific testing.

## Ungated Actions Inventory

These pages/actions need permission gating when their features are built or extended. Follow the patterns described above.

### Policies — API-ready, UI not yet built

Backend defines `policy:create`, `policy:update`, `policy:delete`. The UI currently has a read-only JSON viewer.

| Action                   | Permission                                       | Pattern to follow                                  |
| ------------------------ | ------------------------------------------------ | -------------------------------------------------- |
| Create policy button     | `policy:create`                                  | `useCredentialPermissions` + `DisabledWithTooltip` |
| Edit/Delete row actions  | `policy:update`/`policy:delete`                  | Same                                               |
| Project-scoped policies  | `policy:update` with `resourceId: 'project:...'` | Scoped `useCanI`                                   |
| Roles create/edit/delete | `role:create`/`role:update`/`role:delete`        | `useRolePermissions` already exists                |

### Executions — partial gating

| Gap                          | Permission       | Pattern to follow                     |
| ---------------------------- | ---------------- | ------------------------------------- |
| Executions list page guard   | `execution:read` | Add `requiredPermissions` to nav item |
| Execution detail route guard | `execution:read` | `SynEmptyStateAccessDenied` on 403    |
| Future rerun action          | `execution:run`  | `DisabledWithTooltip`                 |

**Note**: Approval permission gating is complete for UI components (list page, nav item, decision actions) with comprehensive unit tests. E2E test coverage in `e2e/permission-gating.spec.ts` for the viewer/auditor/user roles is recommended as a follow-up to verify end-to-end permission flows.

### Integrations — gated

Integration permission gating uses `useIntegrationPermissions` hook checking `integration:create`, `integration:update`, `integration:delete`.

| Action                      | Permission           | Implementation                                        |
| --------------------------- | -------------------- | ----------------------------------------------------- |
| Configure (create)          | `integration:create` | `DisabledWithTooltip` on list page + route guard      |
| Edit integration            | `integration:update` | `DisabledWithTooltip` on detail toolbar + route guard |
| Enable/disable integration  | `integration:update` | `Tooltip` on disabled `Switch`                        |
| Validate integration        | `integration:update` | `isAriaDisabled` + `tooltipProps` on kebab action     |
| Delete integration          | `integration:delete` | `isAriaDisabled` + `tooltipProps` on kebab action     |
| Enable/disable tools/models | `integration:update` | `canUpdate` prop on tab checkboxes + save button      |
| Refresh tools/models        | `integration:update` | `isAriaDisabled` on refresh button                    |

### Settings — minor UX gap

Settings gating is functionally complete. Minor gap: no loading spinner during initial `useCanI` resolution — authorized users may briefly flash the access-denied state. Consider using `isChecking` to show a spinner.

### Transfer Identity wizard

No `routePermission` on route. When gated, add `routePermission` with `user_identity:attach`.
