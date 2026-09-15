# Approval-Execution Integration

This document describes how approvals are displayed and managed within the execution visualizer. It covers fetching approval data, rendering the review interface, decision submission, and permission-based UI controls.

## Overview

When a workflow execution reaches an approval node, the execution visualizer displays a waiting state on the canvas. Users can click the node to open a review view where they can examine approval details, see what happens next, and submit a decision (approve/reject).

## Architecture

The execution-side approval hooks follow a **4-layer architecture** (documented in `useExecutionNodeClick.ts`):

1. **Data** (Layer 1): `useFetchPendingApprovals`, `useFetchApprovalForNode`, `useFetchApprovalForUrlParam` — fetch approval data lazily on demand
2. **State** (Layer 2): `useExecutionApprovals` — manages multi-approval array and navigation index
3. **Interaction** (Layer 3): `useExecutionNodeClick` — routes approval vs. details clicks on the canvas
4. **UI** (Layer 4): `useExecutionApprovalPanel` — panel open/close, URL deep linking, auto-detection

**Deep linking**: Users can link directly to an approval via `/executions/{id}?approval={approvalId}`. The `useFetchApprovalForUrlParam` hook reads the URL param, and `useExecutionApprovalPanel` opens the panel automatically.

**Permission checks**: Two-tier authorization (RBAC + approver list)

## Fetching Approvals

### Hook: `useFetchApprovalForNode`

**Location**: `packages/syntara-ui/src/routes/executions/hooks/useFetchApprovalForNode.ts`

**Signature**:

```typescript
function useFetchApprovalForNode(executionId: string): {
  isLoading: boolean
  fetchForNode: (approvalNodeId: string) => Promise<Approval | null>
  clear: () => void
}
```

**Purpose**: Lazily fetches pending approvals for a specific execution, then filters client-side by `approval_node_id` to find the matching approval. This avoids polling — the fetch is triggered on demand when the user clicks a waiting approval node on the canvas.

**Implementation Details**:

- Uses `approvalsClient.useQuery('get', '/approvals', ...)` with `enabled: false` to disable automatic fetching
- Query params: `execution_id` and `status: 'pending'`
- `fetchForNode(approvalNodeId)` calls `refetch()`, then filters the returned list by canvas `approval_node_id` (pending first, else latest `loop_iteration_path`). Legacy `{nodeId}_iter_{n}` suffixes are a fallback only.
- Returns `null` if no matching approval is found
- `clear()` resets the loading state (e.g., when closing the review view)

**Usage Example**:

```typescript
const { fetchForNode, isLoading, clear } = useFetchApprovalForNode(executionId)

const handleNodeClick = async (nodeId: string) => {
  const approval = await fetchForNode(nodeId)
  if (approval) {
    // Show review view
  }
}
```

## Review View (`ApprovalReviewView`)

**Location**: `packages/syntara-ui/src/routes/executions/ApprovalReviewView.tsx`

**Purpose**: Full-page review interface for pending approvals. Displays approval details, next steps, and a decision form. Only shown to authorized users.

### Props

```typescript
type ApprovalReviewViewProps = {
  approval: Approval
  /** Maps activity IDs to human-readable names from the workflow definition. */
  activityNameMap?: Map<string, string>
  onClose: () => void
}
```

### Permission Checks (Two-Tier)

The view performs two independent checks before allowing a decision:

1. **RBAC permission check**: `useApprovalPermissions()` checks if the user has the `approval:decide` permission
2. **Approver list check**: `useCanDecideApproval(approval)` checks if the user is in `approver_users` or `approver_groups`

Both checks must pass for the user to see the decision form. If either fails, the view redirects to `ApprovalReadOnlyView`.

**SECURITY NOTE**: Client-side checks are for UX only. The backend ALWAYS validates and returns 403 via `ApprovalService._is_user_authorized_approver()`.

### Form State

The decision form uses `react-hook-form` with Zod validation (`approvalDecisionSchema`):

```typescript
const { handleSubmit, setValue, setError, control } = useForm<ApprovalDecisionFormData>({
  resolver: zodResolver(approvalDecisionSchema),
  defaultValues: {
    status: 'approved',
    notes: '',
  },
})
```

- **Decision**: Toggle group (Approve/Reject)
- **Notes**: Optional text area (whitespace is trimmed; empty strings become `null`)

### UI Structure

The view is laid out as a `Stack` with the following sections (top to bottom):

1. **Header**: Title + Cancel/Submit buttons
2. **Summary**: Workflow name, approval initiated timestamp (via `ApprovalSummaryList`)
3. **Next steps**: Two-column description list showing `next_step_approved` and `next_step_rejected`
4. **Approval context**: `SynCodeBlock` displaying the full approval object as JSON
5. **Decision form**: Toggle group + notes field

### Next Steps Display

The `next_step_approved` and `next_step_rejected` fields are rendered using a `NextStepSummary` component:

- **Step name**: Resolved from `activityNameMap` (if available), with a fallback to `step.name`
- **Step type**: Displayed as a compact `Label`
- **Parameters**: Rendered as a compact horizontal `DescriptionList` (excluding `name` from the list)

**Special case**: If `next_step_rejected` is `null`, the view displays "Workflow ends".

### Approval Context

The "Approval context" section displays the full approval object as JSON using `SynCodeBlock`:

```typescript
<SynCodeBlock jsonObject={approval} enableCopy />
```

**IMPORTANT**: The section title is **"Approval context"**, not "Previous Step" or any other label.

## Decision Submission

### Mutation

Decisions are submitted via:

```typescript
approvalsClient.useMutation('patch', '/approvals/{approval_id}')
```

### Request Payload

```typescript
{
  params: { path: { approval_id: approvalId } },
  body: {
    status: 'approved' | 'rejected',
    notes: string | null,  // Trimmed; empty becomes null
  }
}
```

### Success Handling

On successful submission:

1. Invalidate execution queries:
   ```typescript
   queryClient.invalidateQueries({ queryKey: ['get', '/executions/{execution_id}'] })
   ```
2. Invalidate approvals list:
   ```typescript
   queryClient.invalidateQueries({ queryKey: ['get', '/approvals'] })
   ```
3. Show success toast:
   - "Approval submitted" (for approved)
   - "Rejection submitted" (for rejected)
4. Close the review view via `onClose()`

### Error Handling

Uses `useFormMutationErrorHandler` to map backend errors to form field errors:

```typescript
const handleError = useFormMutationErrorHandler(setError)

decisionMutation.mutate(
  { ... },
  {
    onSuccess: ...,
    onError: handleError({ title: 'Failed to submit decision' }),
  }
)
```

## Approval Detail Content (Standalone View)

**Location**: `packages/syntara-ui/src/routes/approvals/ApprovalDetailContent.tsx`

**Purpose**: Reusable approval detail component used by the approvals list and other standalone views (not the execution-integrated review view).

### Key Differences from `ApprovalReviewView`

1. **Layout**: Horizontal action buttons (Approve/Reject) at the top, followed by a summary and collapsible JSON block
2. **Decision flow**: Two-step UI — click button → enter notes → submit
3. **Permission tooltips**: Uses `DisabledWithTooltip` to explain why buttons are disabled
4. **Approver info**: Shows approver usernames and groups in tooltip when user is not authorized

### Approval Context Display

Uses the same `SynCodeBlock` component, but with additional props for expansion:

```typescript
<SynCodeBlock
  jsonObject={approval}
  enableCopy
  enableExpand
  expandTitle="Approval context"
  fillHeight
/>
```

## WebSocket Integration

**Location**: `packages/syntara-ui/src/routes/executions/hooks/useExecutionStreaming.ts`

**Purpose**: Streams execution state updates via WebSocket, including activity status changes.

### Scope

The execution WebSocket connection **does not stream approval data**. It only streams:

- Execution status changes (`running`, `paused`, `completed`, etc.)
- Activity execution updates (status, timestamps, error details)

### Approval Data Refresh

When an approval decision is submitted:

1. The decision mutation invalidates the execution query
2. The execution query refetches, updating the activity status from `waiting_approval` to the next state
3. The canvas re-renders to reflect the new state

**IMPORTANT**: Approval fetching is lazy (on-demand), not streamed. The WebSocket does not push approval objects to the client.

## Permission-Based UI

### Read-Only View

If the user does not have `approval:decide` permission OR is not in the approver list, the review view renders `ApprovalReadOnlyView` instead:

```typescript
if (!isCheckingPermissions && !canDecide) {
  const approverUsernames = approval.approver_users?.map((u) => u.username) ?? []
  const approverGroupNames = approval.approver_groups?.map((g) => g.name) ?? []
  return (
    <ApprovalReadOnlyView
      approval={approval}
      activityNameMap={activityNameMap}
      approverUsernames={approverUsernames}
      approverGroups={approverGroupNames}
      onClose={onClose}
    />
  )
}
```

The read-only view displays:

- Approval summary (workflow name, initiated timestamp, message)
- Approver list (usernames and groups)
- Approval context (JSON block)
- **No decision controls**

### Button States

While permission checks are loading (`isCheckingPermissions`), the Submit button is disabled. Once checks complete, the button is enabled only if `canDecide` is `true`.

## Field Names and Casing

All field names in the approval object use **snake_case** to match the backend API:

- `approval_node_id` (not `approvalNodeId`)
- `next_step_approved` (not `nextStepApproved`)
- `next_step_rejected` (not `nextStepRejected`)
- `workflow_context` (not `workflowContext`)
- `approver_users` (not `approverUsers`)
- `approver_groups` (not `approverGroups`)
- `decision_notes` (not `decisionNotes`)
- `created_at` (not `createdAt`)

TypeScript types from `@syntara/contracts` enforce this casing at compile time.

## Common Patterns

### Resolving Activity Names

Both `ApprovalReviewView` and `ApprovalDetailContent` resolve human-readable names from the workflow definition:

```typescript
const resolveName = (id: string, fallback: string) => lookupMapByApprovalNodeId(activityNameMap, id) ?? fallback

const approvalNodeId = approval.approval_node_id
const resolvedNodeName = lookupMapByApprovalNodeId(activityNameMap, approvalNodeId)
const approvalDisplayName = resolvedNodeName ? `Approval for ${resolvedNodeName}` : approval.name
```

### Formatting Timestamps

All timestamps are formatted via `formatDateTime()` from `utils/dateUtils.ts`:

```typescript
const approvalInitiated = formatDateTime(approval.created_at)
```

### Handling Missing Data

- `next_step_rejected` is optional — when `null`, display "Workflow ends"
- `decision_notes` is optional — only display the notes field if non-empty
- `activityNameMap` is optional — fall back to `approval.name` if not provided

## Testing Considerations

When writing E2E tests for approval-execution integration:

1. **Create approvals with known `approval_node_id`** to test the filtering logic
2. **Mock permission responses** for both RBAC and approver list checks
3. **Verify query invalidation** after decision submission (execution and approvals lists should refetch)
4. **Test unauthorized access** — verify read-only view is shown
5. **Test WebSocket updates** — verify canvas updates after decision submission (via query refetch, not WebSocket push)

## Summary

The approval-execution integration provides:

- **Lazy fetching**: On-demand approval loading via `useFetchApprovalForNode(executionId)`
- **Review interface**: Full-page form with next steps preview and context display
- **Two-tier permissions**: RBAC + approver list checks (both required)
- **Decision submission**: PATCH mutation with query invalidation
- **Read-only fallback**: Unauthorized users see approval details without decision controls
- **WebSocket streaming**: Execution state only (not approval data)

All field names use snake_case. The approval context section is labeled "Approval context" in the UI.

## Related Documentation

- [Approval Builder Integration](./approval-builder-integration.md) — Form configuration and workflow store integration
- [Approval UI Architecture](./approval-ui-architecture.md) — Approvals list page, bulk actions, permission-based UI
- [Approval Overview](../../../backend/docs/approvals/approval-overview.md) — Backend approval system architecture
- [Approval Authorization Model](../../../backend/docs/approvals/approval-authorization-model.md) — Two-tier authorization (RBAC + approver lists)
