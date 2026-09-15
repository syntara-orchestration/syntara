# Approval Node — Builder Integration

## Overview

The Approval node creates a human approval gate that pauses workflow execution until an authorized user or group member approves or rejects the request. This document describes the complete integration between the node registration, form component, validation schema, and workflow store.

## Node Registration

**File**: `packages/syntara-ui/src/routes/builder/registry/nodes/registerApprovalNode.ts`

### Registry Properties

```typescript
NodeRegistry.register<ApprovalFormSubmitData>({
  id: RegistryNodeId.APPROVAL,
  label: 'Approval',
  icon: RhUiUserCheckIcon,
  category: 'logic',
  description: 'Wait for approval or human input before continuing',
  keywords: ['approve', 'approval', 'review', 'manual', 'gate', 'checkpoint'],
  order: 50,
  formComponent: ApprovalNodeForm,
  enabled: true,
  onSubmit: (data, onSuccess, onError) => {
    /* ... */
  },
})
```

**Key Points**:

- **No `DetailsComponent`** — the approval node uses the standard activity details view, not a custom renderer
- **Category**: `'logic'` — appears in the logic section of the node picker
- **Order**: `50` — positioned after control flow nodes, before utility nodes
- **Form Component**: `ApprovalNodeForm` — handles all user input

### onSubmit Handler

The `onSubmit` handler transforms the form data into an approval activity and adds it to the workflow store:

```typescript
onSubmit: (data, onSuccess, onError) => {
  try {
    const baseName = getDefaultNodeBaseName({
      nodeTypeId: RegistryNodeId.APPROVAL,
      label: 'Approval',
    })
    const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
      createApprovalActivity({
        id,
        name,
        approver_users: data.approver_users,
        approver_groups: data.approver_groups,
        prompt: data.prompt,
        fallback_decision: data.fallback_decision,
        decision_window: data.decision_window,
        settings: data.settings,
      })
    )

    useWorkflowStore.getState().addActivity(activity)
    onSuccess(activityId)
  } catch (error) {
    onError(error instanceof Error ? error.message : 'Failed to add approval step')
  }
}
```

**Field Mapping** (form → store):

- `data.name` → activity name
- `data.approver_users` → activity config (array of usernames)
- `data.approver_groups` → activity config (array of group names)
- `data.prompt` → activity config (approval message text)
- `data.fallback_decision` → activity config (`'approve'` | `'reject'`)
- `data.decision_window` → activity config (seconds, integer)
- `data.settings` → activity settings (`continue_on_failure`, `continue_on_cancel`)

**All field names use `snake_case` to match the backend API contract.**

## Form Schema & Validation

**File**: `packages/syntara-ui/src/routes/builder/node-forms/approvalFormSchema.ts`

### Zod Schema

```typescript
import { z } from 'zod'
import { nodeSettingsSchema } from './shared/nodeSettingsSchema'

const MAX_APPROVER_USERS = 100
const MAX_APPROVER_GROUPS = 50

export const approvalFormSchema = z.object({
  name: z.string(),
  approver_users: z
    .array(z.string())
    .max(MAX_APPROVER_USERS, `Cannot select more than ${MAX_APPROVER_USERS} users`)
    .optional(),
  approver_groups: z
    .array(z.string())
    .max(MAX_APPROVER_GROUPS, `Cannot select more than ${MAX_APPROVER_GROUPS} groups`)
    .optional(),
  prompt: z.string().optional(),
  fallback_decision: z.enum(['approve', 'reject']).optional(),
  decision_window: z.number().int().positive().optional(),
  settings: nodeSettingsSchema.optional(),
})

export type ApprovalFormData = z.infer<typeof approvalFormSchema>
```

### Validation Constraints

| Field               | Type                    | Constraints                           | Default     |
| ------------------- | ----------------------- | ------------------------------------- | ----------- |
| `name`              | `string`                | Required                              | `''`        |
| `approver_users`    | `string[]`              | Optional, max 100 items               | `[]`        |
| `approver_groups`   | `string[]`              | Optional, max 50 items                | `[]`        |
| `prompt`            | `string`                | Optional                              | `''`        |
| `fallback_decision` | `'approve' \| 'reject'` | Enum, optional                        | `'reject'`  |
| `decision_window`   | `number`                | Optional, integer, positive (seconds) | `undefined` |
| `settings`          | `NodeSettings`          | Optional                              | `{}`        |

**Why groups have a lower limit (50 vs 100)**:
Groups expand into individual members. A single group can contain many users, multiplying the effective number of authorized approvers. The lower limit prevents DoS attacks and UI performance issues from excessively large permission sets.

### Form Submit Data Type

```typescript
export type ApprovalFormSubmitData = {
  name: string
  approver_users?: string[] // Usernames who can approve
  approver_groups?: string[] // Group names whose members can approve
  prompt?: string
  fallback_decision?: 'approve' | 'reject'
  decision_window?: number // How long (in seconds) the approver has to respond
  settings?: NodeSettings
  metadata?: { [key: string]: unknown }
  outputs?: {
    approved?: boolean
    decided_by?: string
    decided_at?: string
    decision_notes?: string
  }
}
```

**Note**: The `metadata` and `outputs` fields are present in the type but not surfaced in the form UI. They are populated at runtime by the workflow engine.

## Form Component Structure

**File**: `packages/syntara-ui/src/routes/builder/node-forms/ApprovalNodeForm.tsx`

### Component Hierarchy

```
ApprovalNodeForm
├── FormProvider (react-hook-form)
│   └── NodeFormContainer
│       └── ApprovalFormFields
│           └── NodeFormTabsLayout
│               ├── Parameters Tab (default)
│               │   ├── ActivityNameField (in header)
│               │   ├── ApproverUsersSelect
│               │   ├── ApproverGroupsSelect
│               │   ├── TextArea (prompt)
│               │   ├── FormSelect (fallback_decision)
│               │   └── DurationInput (decision_window)
│               └── Settings Tab
│                   └── NodeSettingsForm
```

### Key Hooks

| Hook                        | Import Path                          | Purpose                                       |
| --------------------------- | ------------------------------------ | --------------------------------------------- |
| `useForm`                   | `react-hook-form`                    | Form state management                         |
| `useFormContext`            | `react-hook-form`                    | Access form state in child components         |
| `useWatch`                  | `react-hook-form`                    | Watch specific field values                   |
| `Controller`                | `react-hook-form`                    | Controlled components (selects)               |
| `useApprovalDecideUsers`    | `./useApprovalDecideUsers`           | Fetch users with `approval:decide` permission |
| `useApprovalDecideGroups`   | `./useApprovalDecideGroups`          | Fetch all groups (filtered client-side)       |
| `useWorkflowEngineDefaults` | `../hooks/useWorkflowEngineDefaults` | System default timeout values                 |
| `useIsVersionView`          | `../VersionViewContext`              | Disable editing in version view               |
| `useWorkflowStore`          | `../../../stores/useWorkflowStore`   | Get workflow's project ID                     |

### Approver Selection

#### User Selection

```typescript
const { users, isLoading: isLoadingUsers } = useApprovalDecideUsers(workflowProjectId)

<Controller
  name="approver_users"
  control={control}
  render={({ field: { value, onChange } }) => (
    <ApproverUsersSelect
      value={value ?? []}
      onChange={onChange}
      users={users}
      isLoading={isLoadingUsers}
      validationError={validationErrors?.approver_users}
    />
  )}
/>
```

**`useApprovalDecideUsers(projectId: string | undefined)`**:

- Fetches users with `approval:decide` permission for the workflow's project
- Returns `{ users: ApproverUser[], isLoading: boolean }`
- Each user: `{ id: string, username: string }`
- Filters to users who can decide approvals in the workflow's project context

#### Group Selection

```typescript
const { groups, isLoading: isLoadingGroups } = useApprovalDecideGroups()

<Controller
  name="approver_groups"
  control={control}
  render={({ field: { value, onChange } }) => (
    <ApproverGroupsSelect
      value={value ?? []}
      onChange={onChange}
      groups={groups}
      isLoading={isLoadingGroups}
      validationError={validationErrors?.approver_groups}
    />
  )}
/>
```

**`useApprovalDecideGroups()`**:

- Fetches all available groups
- Returns `{ groups: ApproverGroup[], isLoading: boolean }`
- Each group: `{ id: string, name: string }`
- Groups are not pre-filtered by permission; authorization happens at runtime when a group member attempts to decide

**Empty Group Warning**:
The groups field includes a help popover with the message: "If a selected group has no members at approval time, that group will be ignored."

### Prompt Field

```typescript
<FormGroup label="Message" fieldId="approval-prompt">
  <TextArea
    {...register('prompt')}
    id="approval-prompt"
    placeholder="Please approve this deployment to production"
    rows={3}
    isDisabled={isVersionView}
  />
</FormGroup>
```

- User-facing label: **"Message"**
- Field name in form data: `prompt`
- Placeholder text suggests typical use case
- No character limit enforced client-side

### Fallback Decision

Implemented in `FallbackDecisionField`. The dropdown is coupled to **effective continue on failure**, resolved the same way the engine does: node `settings.continue_on_failure` → admin `workflow_engine.continue_on_failure` → `false`.

**Default**: `'reject'`

**Behavior**:

- If the decision window expires or the approval request cannot be delivered, the workflow uses the fallback decision
- Requires effective continue on failure to be on; otherwise the activity fails and fallback is ignored
- When effective continue on failure is off, the dropdown is disabled, warning helper text explains why, and an **Enable continue on failure** link sets `settings.continue_on_failure: true`
- Warning copy differs for system default (stop) vs an explicit node-level stop
- The enable link and disabled-state tooltip are hidden in version (read-only) view

### Decision Window

```typescript
const { defaults } = useWorkflowEngineDefaults()
const approvalTimeoutDefault = defaults?.timeoutSeconds.approval ?? null

<FormGroup label="Decision window" fieldId="approval-decision-window">
  <Stack hasGutter>
    <StackItem>
      <DurationInput
        value={decisionWindow}
        onChange={(val) => setValue('decision_window', val, { shouldDirty: true })}
        idPrefix="approval-decision-window"
        isDisabled={isVersionView}
      />
    </StackItem>
    <StackItem>
      <HelperText>
        <HelperTextItem>
          {approvalTimeoutDefault !== null
            ? `How long the approver has to respond before the request expires. Falls back to system default (${formatDuration(approvalTimeoutDefault)}) if not set.`
            : 'How long the approver has to respond before the request expires. Falls back to system default if not set.'}
        </HelperTextItem>
      </HelperText>
    </StackItem>
  </Stack>
</FormGroup>
```

**`DurationInput` Component**:

- Converts seconds ↔ hours/minutes/seconds
- User edits hours, minutes, seconds separately
- Stores combined value as total seconds in form state
- System default is fetched from backend via `useWorkflowEngineDefaults()`

## Settings Tab

```typescript
const settingsContent = (
  <NodeSettingsForm
    supportsTimeout={false}
    continueOnFailureHelp="When enabled and the approval cannot complete (decision window expired or send failure), the workflow proceeds. The outcome is determined by the fallback decision in the approval config."
  />
)
```

### Why `supportsTimeout: false`

The approval node does NOT support the standard activity timeout because it has its own domain-specific timeout: the **decision window**.

- **Standard activity timeout**: How long the activity can run before being killed
- **Decision window**: How long the approver has to respond before the request expires

The decision window is the correct timeout mechanism for approval semantics. Exposing the standard activity timeout would create confusion about which timeout applies.

### Settings Fields

When `supportsTimeout: false`, `NodeSettingsForm` renders:

- **Continue on failure** (`settings.continue_on_failure`):
  - When enabled and the approval cannot complete (decision window expired or send failure), the workflow proceeds
  - The outcome is determined by the `fallback_decision` in the approval config
  - When disabled, the activity fails and the workflow stops (unless the workflow-level error handling is configured)

- **Continue on cancel** (`settings.continue_on_cancel`):
  - When enabled, if the workflow execution is cancelled while the approval is pending, the workflow proceeds to the next step
  - When disabled, the workflow stops immediately

**Note**: The timeout field is hidden because `supportsTimeout: false`.

## Store Integration

### Activity Creation

The `onSubmit` handler calls `createApprovalActivity()` from the workflow store:

```typescript
const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
  createApprovalActivity({
    id,
    name,
    approver_users: data.approver_users,
    approver_groups: data.approver_groups,
    prompt: data.prompt,
    fallback_decision: data.fallback_decision,
    decision_window: data.decision_window,
    settings: data.settings,
  })
)
```

**`buildNamedActivity` Helper**:

- Ensures unique activity names across the workflow
- Auto-increments duplicates: `Approval`, `Approval 1`, `Approval 2`, etc.
- Returns `{ activityId, activity }` for insertion into the store

### Adding to Workflow

```typescript
useWorkflowStore.getState().addActivity(activity)
onSuccess(activityId)
```

After creating the activity object:

1. Call `addActivity(activity)` on the workflow store
2. Invoke `onSuccess(activityId)` callback to close the form and select the new node
3. The builder canvas auto-updates via Zustand subscriptions

## Approval Status Badges

**File**: `packages/syntara-ui/src/routes/approvals/approvalUtils.tsx`

The `ApprovalStatusBadges` component renders status badges for approval requests in the approvals list view and execution details.

### Status Mapping

```typescript
const statusMap: Record<ApprovalStatus, 'info' | 'success' | 'danger' | 'warning'> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  expired: 'warning',
  cancelled: 'info',
}

const statusIcons: Record<ApprovalStatus, React.ComponentType<{ className?: string }>> = {
  pending: RhUiWarningFillIcon,
  approved: RhUiLikeFillIcon,
  rejected: RhUiDislikeFillIcon,
  expired: RhUiWarningFillIcon,
  cancelled: RhUiWarningFillIcon,
}
```

### Component Usage

```typescript
<ApprovalStatusBadges status={approval.status} />
```

**Rendered Output**:

- `pending` → Yellow badge with warning icon, "Pending"
- `approved` → Green badge with thumbs-up icon, "Approved"
- `rejected` → Red badge with thumbs-down icon, "Rejected"
- `expired` → Yellow badge with warning icon, "Expired"
- `cancelled` → Blue badge with warning icon, "Cancelled"

**Implementation**:

```typescript
export function ApprovalStatusBadges(props: Readonly<{ status?: ApprovalStatus | null }>) {
  if (!props.status) {
    return null
  }

  const IconComponent = statusIcons[props.status]
  const capitalizedStatus = props.status.charAt(0).toUpperCase() + props.status.slice(1)

  return (
    <SynLabel variant="outline" status={statusMap[props.status]} icon={<IconComponent />}>
      {capitalizedStatus}
    </SynLabel>
  )
}
```

**Uses `SynLabel` for system-generated status indicators** (per `.claude/skills/frontend-coding-standards/SKILL.md` §12).

## Builder Approval Handling (Execution Context)

The builder also handles approval interactions when viewing a live or recent execution overlay. The `useBuilderApproval` hook (`packages/syntara-ui/src/routes/builder/hooks/useBuilderApproval.ts`) bridges the execution-side approval system into the builder canvas:

- **Badge click detection**: Uses `EXECUTION_BADGE_SELECTOR` (a CSS data-attribute selector from `ExecutionStatusBadge.tsx`) to distinguish clicks on the execution status badge from normal node clicks
- **Approval view**: When a user clicks a waiting-approval badge, the hook fetches the pending approval and opens `ApprovalReviewModal` inline in the builder
- **Auto-detection**: During live runs, `useAutoApprovalDetection` monitors for newly waiting approval nodes and opens the review view automatically
- **Activity name map**: Builds a `Map<activityId, activityName>` from the current workflow definition for human-readable display in the review view

## Known Limitations

### Group Permission Filtering

`useApprovalDecideGroups` (`packages/syntara-ui/src/routes/builder/node-forms/useApprovalDecideGroups.ts`) returns **all groups** without filtering by `approval:decide` permission. Users can select groups whose members lack the required permission, creating approvals that no group member can decide (effectively hanging forever). The helper text warns about empty groups, but there is no check for permission eligibility.

**Why**: The `/authz/who_can` endpoint returns users, not groups. Client-side filtering would require N×M API calls (N groups × M members). A proper fix requires a backend `/authz/which_groups_can` endpoint.

**Mitigation**: Backend validates group membership at decision time, so unauthorized decisions are rejected. The risk is UX-level: a misconfigured approval hangs until the decision window expires and the fallback decision takes effect.

## Summary

### Data Flow

1. **User opens approval node form** → `ApprovalNodeForm` renders with default values
2. **User selects approvers** → `useApprovalDecideUsers` and `useApprovalDecideGroups` populate dropdowns
3. **User configures settings** → Form state tracked by `react-hook-form`
4. **User submits form** → `approvalFormSchema` validates via Zod
5. **Validation passes** → `onSubmit` handler transforms data to `ApprovalFormSubmitData`
6. **Create activity** → `buildNamedActivity` + `createApprovalActivity` produce store object
7. **Add to store** → `useWorkflowStore.getState().addActivity(activity)`
8. **Success callback** → Form closes, new node selected on canvas

### Key Patterns

- **All field names use `snake_case`** to match backend API contract
- **No `DetailsComponent`** in registration — uses standard activity details view
- **Zod validation** with `max()` constraints (100 users, 50 groups)
- **Controlled components** via `react-hook-form` `Controller` for selects
- **Permission-filtered approver lists** via `useApprovalDecideUsers(projectId)`
- **System defaults** fetched via `useWorkflowEngineDefaults()` for decision window
- **Settings tab** with `supportsTimeout: false` (decision window replaces activity timeout)
- **Status badges** use `SynLabel` with `variant="outline"` and status-specific icons

## Related Documentation

- [Approval UI Architecture](./approval-ui-architecture.md) — Approvals list page, bulk actions, permission-based UI
- [Approval Execution Integration](./approval-execution-integration.md) — Review view and decision submission during execution
- [Approval Overview](../../../backend/docs/approvals/approval-overview.md) — Backend approval system architecture
- [Approval Execution Pattern](../../../backend/docs/approvals/approval-execution-pattern.md) — Workflow integration, timeout resolution, signal protocol
