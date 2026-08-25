# Approval UI Architecture

## Overview

The Approval UI provides a comprehensive interface for viewing and managing approval requests. It supports both global (all projects) and project-scoped views, permission-based row selection, bulk approve/reject actions, and client-side sorting with cursor pagination.

**Key Features:**

- Permission-gated access (read + decide permissions)
- Project filtering via `useProjectSelector` hook
- Per-approval RBAC permission checking
- Approver list enforcement (user/group matching)
- Bulk approve/reject with optimistic UI updates
- Client-side sorting with cursor pagination
- Grouped display when viewing all projects

## Page Architecture

### Entry Point: `Approvals` Component

**File:** `packages/syntara-ui/src/routes/approvals/Approvals.tsx`

The top-level component performs permission checks via `useApprovalPermissions()` before delegating to `ApprovalsPage`:

1. `useApprovalPermissions()` checks `approval:read` permission (via `useCanI`)
2. While checking: show loading spinner
3. If denied: show `EmptyStateAccessDenied`
4. If allowed: render `ApprovalsPage`

### Main Page: `ApprovalsPage` Component

`ApprovalsPage` orchestrates six hooks that each manage one concern:

| Hook                       | Purpose                                                                                       |
| -------------------------- | --------------------------------------------------------------------------------------------- |
| `useProjectSelector()`     | Project filtering — returns `ProjectSelector` ReactNode, `selectedProjectId`, `isAllProjects` |
| `useCursorPagination()`    | Pagination state + filter params                                                              |
| `useTableSort()`           | Sort column and direction (default: `requested_at` desc)                                      |
| `useApprovalsData()`       | Fetch, enrich, group, and sort approvals                                                      |
| `useApprovalSelection()`   | Checkbox selection state with filter/sort awareness                                           |
| `useBulkApprovalActions()` | Bulk approve/reject mutation + dialog state                                                   |

See each hook's source file for signatures and implementation (listed in [Key Files Reference](#key-files-reference)).

## Data Fetching & Enrichment

### `useApprovalsData` Hook

**File:** `packages/syntara-ui/src/routes/approvals/useApprovalsData.ts`

Fetches approvals from the API, enriches them with workflow metadata, and performs client-side sorting.

**Data Flow:**

1. **Query Selection:**
   - If `isAllProjects`: fetch from `GET /approvals` (all projects)
   - Else: fetch from `GET /projects/{project_id}/approvals` (single project)

2. **Enrichment:** Extracts workflow metadata from `approval.workflow_context` — maps `workflow_name` → `approvalName` (fallback to `approval.id`) and `workflow_version_id` → `workflowId`, producing `ApprovalWithDetails` objects.

3. **Grouping (All Projects Only):** Groups approvals by `project_id` and maps each to its `ProjectRead` object, returning `Map<projectId, { project, approvals }>`.

4. **Client-Side Sorting:** Sorts by `sortColumn` (approvalName, workflowName, requested_at, decided_at, status) with `sortDirection` (asc/desc). Sorts current page only (not server-side).

**Field Names:**

- API fields: `created_at`, `decided_at`, `status`, `project_id`, `workflow_context`
- Enriched fields: `approvalName`, `workflowName`, `workflowId`

## Permission-Based Selection

Checkbox selection is gated by **two independent permission checks**:

1. **RBAC Permission:** `approval:decide` at system or project level
2. **Approver List:** User or user's group must be in `approval.approver_users` or `approval.approver_groups`

Both checks must pass for a checkbox to be enabled.

### `useApprovalDecideProjects` Hook

**File:** `packages/syntara-ui/src/routes/approvals/useApprovalDecideProjects.ts`

Fetches all user permissions via `useAllPermissions()` and parses which projects have `approval:decide` permission. Returns `canDecideAllProjects` (boolean for system-level permission) and `canDecideProjectNames` (Set of project names with project-scoped permission).

**Caveat:** The `what_can_i` endpoint returns project **names**, not IDs. The UI must map `approval.project_id` to `project.name` for permission checks. If a project is renamed after permissions are granted, the name-based lookup fails until permissions are re-evaluated — see [Known Limitations](#known-limitations).

### `canDecideOnApproval` Function

**File:** `packages/syntara-ui/src/routes/approvals/canDecideOnApproval.ts`

Determines if the user has RBAC permission to decide on a specific approval:

1. If `canDecideAllProjects`: return `true` (system-level permission)
2. If approval has no `project_id`: return `false` (conservative)
3. Find project by `approval.project_id` in `projects` array
4. If project not found: return `false` (deleted or no read access)
5. Check if `canDecideProjectNames.has(project.name)`

### `useSelectableApprovalIds` Hook

**File:** `packages/syntara-ui/src/routes/approvals/useSelectableApprovalIds.ts`

Computes which approvals should have enabled checkboxes. Fetches the current user's groups via `GET /users/{user_id}/groups`, then for each approval checks both RBAC permission (from `approvalPermissions` map) and approver list membership (via `computeCanDecideOnApproval`). Returns a `Set<string>` of selectable approval IDs.

**Criteria for Selectable Approval:**

1. `approval.status === 'pending'` (not already decided)
2. `canDecideOnThisApproval` (RBAC permission via `canDecideOnApproval`)
3. `canDecideBasedOnApproverList` (user/group in approver lists)
4. Not loading permissions (`isLoadingDecideProjects` and `isLoadingUserGroups` both false)

## Selection State Management

### `useApprovalSelection` Hook

**File:** `packages/syntara-ui/src/routes/approvals/useApprovalSelection.ts`

Manages checkbox selection state with filter/sort awareness and pagination support using `useReducer`.

**Actions:**

| Action                   | Trigger                                  | Behavior                                                                |
| ------------------------ | ---------------------------------------- | ----------------------------------------------------------------------- |
| `SYNC_APPROVALS`         | `enrichedApprovals` changes (pagination) | Keeps off-page selections; removes selections for non-pending approvals |
| `RESET_ON_FILTER_CHANGE` | Filters or sort change                   | Clears all selections to prevent stale state                            |
| `SELECT_ALL`             | Header checkbox toggled                  | Only selects approvals in `selectableApprovalIds` set                   |
| `SELECT_ROW`             | Individual checkbox toggled              | Only allows selecting pending approvals                                 |
| `CLEAR_SELECTION`        | Bulk action success                      | Removes all selections                                                  |

**Header Checkbox State:**

- Indeterminate: some pending approvals selected (not all)
- Checked: all pending approvals on current page selected
- Unchecked: no pending approvals selected

## Bulk Actions

### `useBulkApprovalActions` Hook

**File:** `packages/syntara-ui/src/routes/approvals/useBulkApprovalActions.ts`

Handles bulk approve/reject mutations via `POST /approvals/batch`. Manages dialog open/close state for both approve and reject dialogs.

**Batch Endpoint:**

- **URL:** `POST /approvals/batch`
- **Request body:** Array of `{ approval_id, status, notes }` decisions
- **Response:** `{ total_success, total_failed }`

**Success Handling:**

- Full success (`total_failed === 0`): Green success alert
- Partial success (`total_failed > 0`): Yellow warning alert (persistent)
- Total failure: Error state via `useMutationErrorHandler`

### Bulk Action Dialogs

**Files:** `packages/syntara-ui/src/routes/approvals/BulkApproveDialog.tsx`, `BulkRejectDialog.tsx`

Both dialogs accept `isOpen`, `onClose`, `onConfirm(note)`, `approvalCount`, and optional `isLoading`. They provide an optional note field (max 1000 chars, trimmed before submission) and use a `key` prop reset pattern to clear the note field on close.

## Status Badges

### `ApprovalStatusBadges` Component

**File:** `packages/syntara-ui/src/routes/approvals/approvalUtils.tsx`

Renders a status badge using `SynLabel` with `variant="outline"` and status-specific icons.

| Status      | Color   | Icon                  | Label     |
| ----------- | ------- | --------------------- | --------- |
| `pending`   | Warning | `RhUiWarningFillIcon` | Pending   |
| `approved`  | Success | `RhUiLikeFillIcon`    | Approved  |
| `rejected`  | Danger  | `RhUiDislikeFillIcon` | Rejected  |
| `expired`   | Warning | `RhUiWarningFillIcon` | Expired   |
| `cancelled` | Info    | `RhUiWarningFillIcon` | Cancelled |

## Project Filtering

### `useProjectSelector` Hook

**File:** `packages/syntara-ui/src/hooks/useProjectSelector.tsx`

Returns a `ProjectSelector` ReactNode (PatternFly Select dropdown with typeahead, favorites, and "Create project" option) along with selected project state.

**Key return values:**

- `selectedProject`: Current project object (null if "All projects" selected)
- `selectedProjectId`: Raw ID from Zustand store (persists across navigation)
- `stableProjectId`: Stable ID for API queries (handles typeahead filter edge cases)
- `isAllProjects`: `true` when "All projects" selected
- `ProjectSelector`: PatternFly Select dropdown ReactNode

**State Persistence:** Uses `useProjectStore` (Zustand with localStorage) to persist selected project ID, name, and favorites list across page navigation.

## WebSocket Updates

**Scope:** WebSockets are **NOT** used in the Approval UI for data fetching.

- **Execution Visualizer:** Uses WebSocket for real-time workflow execution updates (see [`docs/execution-visualizer-protocol.md`](../execution-visualizer-protocol.md))
- **Approval List:** Uses REST API with manual refetch after bulk actions

## Known Limitations

### Renamed Projects Break Permission Checks

The `what_can_i` authorization endpoint returns project **names**, not IDs. The `canDecideOnApproval` function (`packages/syntara-ui/src/routes/approvals/canDecideOnApproval.ts`) maps `approval.project_id` → `project.name` → `canDecideProjectNames.has(name)`. If a project is renamed after permissions are granted, the stale name in `canDecideProjectNames` no longer matches the project's current name, and the permission check fails silently — the user loses the ability to decide on approvals in that project until their permissions are re-evaluated.

**Mitigation:** System-level `approval:decide` permission is unaffected (it bypasses the name lookup). Only project-scoped permissions are vulnerable.

## Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ Approvals Component (Route Entry)                                       │
│ ├─ useApprovalPermissions() → approval:read check                       │
│ └─ If allowed → delegate to ApprovalsPage                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ApprovalsPage Component                                                  │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useProjectSelector()                                                 │ │
│ │ → ProjectSelector (ReactNode), selectedProjectId, isAllProjects     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useCursorPagination()                                                │ │
│ │ → cursor, filters, queryParams, handleFilterChange                  │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useTableSort()                                                       │ │
│ │ → activeSortIndex, sortDirection, getSortParams                     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useApprovalsData()                                                   │ │
│ │ ├─ Fetch: GET /approvals OR /projects/{id}/approvals               │ │
│ │ ├─ Enrich: Extract workflow_name, workflow_version_id              │ │
│ │ ├─ Group: By project_id (if isAllProjects)                         │ │
│ │ └─ Sort: Client-side by sortColumn + sortDirection                 │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useApprovalDecideProjects()                                          │ │
│ │ ├─ Fetch: GET /what_can_i (all permissions)                        │ │
│ │ └─ Parse: canDecideAllProjects, canDecideProjectNames (Set)        │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Per-Approval Permission Check                                        │ │
│ │ ├─ canDecideOnApproval(approval, canDecideAllProjects, ...)        │ │
│ │ └─ Map project_id → project.name → check canDecideProjectNames     │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useSelectableApprovalIds()                                           │ │
│ │ ├─ Fetch: GET /users/{id}/groups (current user groups)            │ │
│ │ ├─ Check: RBAC (approvalPermissions) + Approver List              │ │
│ │ └─ Return: Set<approvalId> for enabled checkboxes                 │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useApprovalSelection()                                               │ │
│ │ ├─ State: selectedIds, lastApprovals, lastFilters                  │ │
│ │ ├─ Actions: SELECT_ALL, SELECT_ROW, SYNC_APPROVALS, CLEAR          │ │
│ │ └─ Behaviors: Filter-aware reset, pagination sync                  │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ useBulkApprovalActions()                                             │ │
│ │ ├─ Mutation: POST /approvals/batch                                 │ │
│ │ ├─ Dialog State: bulkApproveDialogOpen, bulkRejectDialogOpen      │ │
│ │ └─ Handlers: handleBulkApprove, handleBulkReject                   │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
│                                                                           │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Render                                                               │ │
│ │ ├─ SynPageHeader (title, ProjectSelector, ApprovalsBulkActions)     │ │
│ │ ├─ FilterBar (name, status filters)                                │ │
│ │ ├─ ApprovalsTableHead (sort, select-all checkbox)                  │ │
│ │ ├─ GroupedApprovalsTableBody (if isAllProjects)                    │ │
│ │ │   OR FlatApprovalsTableBody                                      │ │
│ │ ├─ PaginationFooter (cursor-based)                                 │ │
│ │ └─ BulkApproveDialog / BulkRejectDialog                            │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Files Reference

### Core Components

- `packages/syntara-ui/src/routes/approvals/Approvals.tsx` — Main page component
- `packages/syntara-ui/src/routes/approvals/ApprovalsTableBody.tsx` — Table body (flat + grouped)
- `packages/syntara-ui/src/routes/approvals/ApprovalsTableHead.tsx` — Table header
- `packages/syntara-ui/src/routes/approvals/ApprovalsBulkActions.tsx` — Bulk action toolbar
- `packages/syntara-ui/src/routes/approvals/BulkApproveDialog.tsx` — Approve dialog
- `packages/syntara-ui/src/routes/approvals/BulkRejectDialog.tsx` — Reject dialog

### Hooks

- `packages/syntara-ui/src/routes/approvals/useApprovalsData.ts` — Data fetching + enrichment
- `packages/syntara-ui/src/routes/approvals/useApprovalPermissions.ts` — Page-level permissions
- `packages/syntara-ui/src/routes/approvals/useApprovalDecideProjects.ts` — Project-scoped decide permissions
- `packages/syntara-ui/src/routes/approvals/useSelectableApprovalIds.ts` — Selectable approval computation
- `packages/syntara-ui/src/routes/approvals/useApprovalSelection.ts` — Selection state management
- `packages/syntara-ui/src/routes/approvals/useBulkApprovalActions.ts` — Bulk action handlers

### Utilities

- `packages/syntara-ui/src/routes/approvals/approvalUtils.tsx` — Status badges
- `packages/syntara-ui/src/routes/approvals/canDecideOnApproval.ts` — Per-approval RBAC check
- `packages/syntara-ui/src/routes/approvals/computeCanDecideOnApproval.ts` — Approver list check
- `packages/syntara-ui/src/routes/approvals/isApprovalSelectable.ts` — Checkbox enabled logic

### Shared Hooks

- `packages/syntara-ui/src/hooks/useProjectSelector.tsx` — Project filtering dropdown
- `packages/syntara-ui/src/hooks/useCursorPagination.tsx` — Cursor pagination + filters
- `packages/syntara-ui/src/hooks/useTableSort.ts` — Sort state management

## Testing Considerations

### Unit Tests

**Per-Hook Coverage:**

- `useApprovalsData.test.tsx` — Data fetching, enrichment, grouping, sorting
- `useApprovalDecideProjects.test.ts` — Permission parsing
- `useSelectableApprovalIds.test.tsx` — Selectable computation
- `useApprovalSelection.test.ts` — Selection state machine
- `useBulkApprovalActions.test.ts` — Bulk action handlers

**Component Tests:**

- `BulkApproveDialog.test.tsx` — Dialog interaction, note handling
- `BulkRejectDialog.test.tsx` — Dialog interaction, note handling
- `ApprovalStatusBadges.test.tsx` — Badge rendering

### E2E Tests

**Key Scenarios:**

1. Permission gating (read denied, decide denied)
2. Project filtering (all projects vs single project)
3. Grouped vs flat table rendering
4. Checkbox selection (enabled/disabled based on permissions + approver list)
5. Select-all behavior
6. Bulk approve/reject with partial success
7. Pagination + filter interaction
8. Sort behavior

**E2E File:** `packages/syntara-ui/e2e/approvals.spec.ts`

## Related Documentation

- [Approval Builder Integration](./approval-builder-integration.md) — Form configuration and workflow store integration
- [Approval Execution Integration](./approval-execution-integration.md) — Review view and decision submission during execution
- [Approval Overview](../../../backend/docs/approvals/approval-overview.md) — Backend approval system architecture
- [Approval Authorization Model](../../../backend/docs/approvals/approval-authorization-model.md) — Two-tier authorization (RBAC + approver lists)
