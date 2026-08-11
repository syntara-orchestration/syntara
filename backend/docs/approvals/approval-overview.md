# Approval Overview

## What is an Approval Request?

An **Approval Request** is a human-in-the-loop decision point in a workflow execution. When a workflow reaches an approval node, it pauses and waits for a human approver to review the context and make a decision (approve or reject). Based on that decision, the workflow proceeds along different execution paths.

Approval requests enable:

- **Manual oversight** of automated workflows before critical operations
- **Decision routing** based on human judgment
- **Audit trails** of who approved what and when
- **Timeout handling** with automatic fallback behavior

## System Architecture

### High-Level Architecture

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                          Workflow Execution Layer                          │
│                                                                            │
│  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐      │
│  │   Activity   │────────▶│   Approval   │────────▶│   Activity   │      │
│  │   (Before)   │         │     Node     │         │   (After)    │      │
│  └──────────────┘         └──────┬───────┘         └──────────────┘      │
│                                   │                                        │
└───────────────────────────────────┼────────────────────────────────────────┘
                                    │ create_approval()
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          Approval Service Layer                            │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │  ApprovalService                                                     │  │
│  │  • create_approval()       - Creates approval request               │  │
│  │  • decide_on_approval()    - Processes user decision                │  │
│  │  • list_approvals()        - Queries with permission filtering      │  │
│  │  • cancel_approval()       - Marks as cancelled                     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│           │                            │                       │            │
│           ▼                            ▼                       ▼            │
│  ┌───────────────┐          ┌──────────────────┐   ┌──────────────────┐  │
│  │ Authorization │          │ Audit Dispatcher │   │ Workflow Client  │  │
│  │   (OPA/Rego)  │          │ (Event Emission) │   │ (Signal Sending) │  │
│  └───────────────┘          └──────────────────┘   └──────────────────┘  │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                            Data Persistence Layer                          │
│                                                                            │
│  ┌──────────────────┐    ┌──────────────────────┐    ┌─────────────────┐ │
│  │ approval_requests│◄───┤approval_approver_users├───▶│     users       │ │
│  │                  │    └──────────────────────┘    └─────────────────┘ │
│  │ • id (PK)        │                                                     │
│  │ • execution_id   │    ┌──────────────────────┐    ┌─────────────────┐ │
│  │ • status         │◄───┤approval_approver_grps├───▶│     groups      │ │
│  │ • decided_by (FK)│    └──────────────────────┘    └─────────────────┘ │
│  │ • timeout_at     │                                                     │
│  │ • workflow_ctx   │                                                     │
│  │ • next_step_*    │                                                     │
│  └──────────────────┘                                                     │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                  │
│                                                                            │
│  ┌───────────────┐           ┌────────────────┐                          │
│  │   Frontend    │           │  Workflow API  │                          │
│  │   (React UI)  │◄─────────▶│   Endpoints    │                          │
│  │               │   REST     │  /approvals/*  │                          │
│  └───────────────┘           └────────────────┘                          │
│         │                                                                  │
│         └──────────────────────────────────────────────────────────────┐  │
│                                                                         │  │
│  User Actions:                                                         │  │
│  • View pending approvals (GET /approvals)                             │  │
│  • Submit decision (PATCH /approvals/{id})                             │  │
│  • Batch decisions (POST /approvals/batch)                             │  │
└────────────────────────────────────────────────────────────────────────────┘
```

### Key Concepts

#### 1. Approval Request Lifecycle

An approval request moves through distinct phases:

- **Creation**: Workflow engine creates request when execution reaches approval node
- **Pending**: Awaiting human decision; approvers can view context and decide
- **Decision**: User submits approve/reject; service validates authorization
- **Resolution**: Workflow continues on approved/rejected path; audit event emitted
- **Timeout**: If decision window expires, fallback routing applies

#### 2. Two-Tier Authorization

Every approval decision requires **both** permission checks to pass:

**Tier 1 - RBAC Permission** (via OPA/Rego):

- System-level: `approval:decide` on any approval
- Project-level: `approval:decide` on approvals in specific project

**Tier 2 - Approver List** (application logic):

- User list: `approver_user_ids` must contain current user ID
- Group list: User must be member of any group in `approver_group_ids`
- Open mode: If both lists empty, any user with RBAC permission can approve

**Service principals** (cert-authenticated) bypass Tier 2 for system operations.

#### 3. Optimistic Locking for Concurrency

The service uses database-level optimistic locking to prevent race conditions:

```sql
UPDATE approval_requests
SET status = 'approved', decided_by = $1, decided_at = NOW()
WHERE id = $2 AND status = 'pending'
RETURNING *;
```

If the `UPDATE` affects 0 rows, another decision already won → raise `AlreadyDecidedError`.

This prevents TOCTOU (Time-Of-Check-Time-Of-Use) vulnerabilities when multiple users decide simultaneously.

#### 4. Workflow Context Preservation

Each approval captures execution context for informed decision-making:

- **Workflow metadata**: Name, version, original inputs
- **Previous step**: What ran before, its output
- **Next steps**: What happens if approved vs rejected
- **Timeout**: When request expires, fallback behavior

This context is stored as JSONB and presented to approvers via the UI.

#### 5. Audit Trail

Every approval lifecycle event emits audit events:

- `ApprovalRequestedEvent`: When approval is created
- `ApprovalDecidedEvent`: When decision is made (approved/rejected)
- `ApprovalCancelledEvent`: When parent workflow is cancelled

Events include:

- Approval ID, execution ID, project ID
- Status, decision, decider identity
- Timestamp, workflow context

### State Lifecycle Diagram

```text
                    ┌─────────────────────────────────────┐
                    │  Workflow Engine Creates Approval   │
                    └──────────────┬──────────────────────┘
                                   │
                                   │ ApprovalService.create_approval()
                                   │ • Validate uniqueness
                                   │ • Insert record
                                   │ • Link approvers
                                   │ • Emit ApprovalRequestedEvent
                                   ▼
                          ┌─────────────────┐
                          │     PENDING     │◄──────────┐
                          └────────┬────────┘           │
                                   │                    │
              ┌────────────────────┼────────────────────┼───────────────────┐
              │                    │                    │                   │
              │ User Decision      │ Timeout Reached    │ Workflow Cancel   │
              │                    │                    │                   │
              ▼                    ▼                    ▼                   │
    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
    │ RBAC Check       │  │ Timeout Handler  │  │ Workflow Signal  │      │
    │ (approval:decide)│  │ Checks Settings  │  │ (Cancellation)   │      │
    └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘      │
             │ ✓                   │                     │                 │
             ▼                     │                     │                 │
    ┌──────────────────┐           │                     │                 │
    │ Approver Check   │           │                     │                 │
    │ (user/group list)│           │                     │                 │
    └────────┬─────────┘           │                     │                 │
             │ ✓                   │                     │                 │
             ▼                     ▼                     ▼                 │
    ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
    │ UPDATE WHERE     │  │ Set EXPIRED      │  │ Set CANCELLED    │      │
    │ status=pending   │  │ Route via        │  │ Stop Waiting     │      │
    │ (Optimistic Lock)│  │ fallback_decision│  │                  │      │
    └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘      │
             │                     │                     │                 │
             │ Success             │                     │                 │
             ▼                     │                     │                 │
    ┌──────────────────┐           │                     │                 │
    │ Set Status:      │           │                     │                 │
    │ APPROVED or      │           │                     │                 │
    │ REJECTED         │           │                     │                 │
    └────────┬─────────┘           │                     │                 │
             │                     │                     │                 │
             ├─────────────────────┴─────────────────────┘                 │
             │                                                             │
             ▼                                                             │
    ┌────────────────────────────────────────────────────┐                 │
    │ Emit Audit Event (ApprovalDecidedEvent)            │                 │
    └──────────────────────┬─────────────────────────────┘                 │
                           │                                               │
                           ▼                                               │
    ┌────────────────────────────────────────────────────┐                 │
    │ Signal Workflow Engine (best-effort, async)        │                 │
    └──────────────────────┬─────────────────────────────┘                 │
                           │                                               │
                           ▼                                               │
             ┌──────────────────────────────┐                              │
             │ Workflow Continues Execution │                              │
             │ • approved → approved edge   │                              │
             │ • rejected → rejected edge   │                              │
             │ • expired → fallback routing │                              │
             │ • cancelled → terminate      │                              │
             └──────────────────────────────┘                              │
                                                                           │
    ┌──────────────────────────────────────────────────────────────────────┘
    │ Retry Logic: If UPDATE affects 0 rows
    │ → Another decision already won (TOCTOU)
    │ → Raise ApprovalAlreadyDecidedError
    └─────────────────────────────────────────────────────────────────────────

Terminal States: APPROVED, REJECTED, EXPIRED, CANCELLED
• Once terminal, status cannot change
• Only PENDING can transition to terminal states
• Service layer enforces state machine invariants
```

### Component Interactions

**Creation Flow:**

1. Workflow engine calls `POST /approvals` with execution context
2. `ApprovalService.create_approval()`:
   - Validates `(execution_id, approval_node_id)` uniqueness
   - Inserts `ApprovalRequest` row with `status=pending`
   - Creates junction table entries for approver users/groups
   - Emits `ApprovalRequestedEvent` to audit system
3. Returns approval ID to workflow engine
4. Workflow execution pauses waiting for decision signal

**Decision Flow:**

1. User views approvals via `GET /approvals` (filtered by permissions)
2. User submits decision via `PATCH /approvals/{id}`
3. `ApprovalService.decide_on_approval()`:
   - **Authorization check**: OPA validates `approval:decide` permission
   - **Approver check**: Validates user in `approver_users` or member of `approver_groups`
   - **Optimistic update**: `UPDATE WHERE status=pending` (prevents TOCTOU)
   - **Audit event**: Emits `ApprovalDecidedEvent` with decision details
   - **Signal workflow**: Best-effort async notification to workflow engine
4. Workflow engine receives signal, continues execution on approved/rejected path

**Batch Decision Flow:**

1. User selects multiple approvals and chooses approve/reject
2. Frontend calls `POST /approvals/batch` with array of decisions
3. Service processes each decision independently:
   - Authorization and approver checks per approval
   - Optimistic locking prevents races
   - Partial success allowed (some succeed, some fail)
4. Returns `{ total_success, total_failed }` counts
5. Frontend shows appropriate success/warning notification

## ApprovalRequest Model Fields

The `ApprovalRequest` model stores all data for an approval gate:

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID | Unique identifier (inherited from BaseResource) |
| `created_at` | datetime | Creation timestamp (inherited from BaseResource) |
| `updated_at` | datetime | Last update timestamp (inherited from BaseResource) |
| `project_id` | UUID | Project this approval belongs to (denormalized from execution) |
| `name` | str | Human-readable name for the approval request |
| `execution_id` | UUID | Parent workflow execution ID (soft reference) |
| `approval_node_id` | str | Activity ID from workflow definition |
| `status` | ApprovalRequestStatus | Current approval status (pending/approved/rejected/expired/cancelled) |
| `timeout_at` | datetime or None | When this request expires |
| `next_step_approved` | dict | First activity that executes if approved (ActivitySummary JSON) |
| `next_step_rejected` | dict or None | First activity that executes if rejected (ActivitySummary JSON) |
| `workflow_context` | dict | Workflow inputs and previous step output (WorkflowContext JSON) |
| `decided_at` | datetime or None | When decision was made |
| `decided_by` | UUID or None | Principal who made the decision (foreign key to principals table) |
| `decision_notes` | str or None | Notes provided with decision |

**Relationships:**

- `decider`: The User who made the decision (loaded via `decided_by` FK)
- `approver_user_records`: List of Users authorized to approve (many-to-many via `approval_approver_users`)
- `approver_group_records`: List of Groups whose members can approve (many-to-many via `approval_approver_groups`)

## Approval Lifecycle

### 1. Creation

When a workflow execution reaches an approval node, the workflow engine creates an `ApprovalRequest`:

1. **Validate uniqueness**: Ensures no approval already exists for this `(execution_id, approval_node_id)` pair
2. **Insert approval record**: Creates the `ApprovalRequest` with status=`pending`
3. **Populate approver lists**: Links authorized users and groups via junction tables
4. **Commit transaction**: All inserts succeed or fail atomically
5. **Emit audit event**: Dispatches `ApprovalRequestedEvent`

The approver configuration uses two junction tables:
- `approval_approver_users`: Links approval to authorized user IDs
- `approval_approver_groups`: Links approval to authorized group IDs

### 2. Decision

An authorized user submits a decision (approve or reject):

1. **Authorization check**: Verifies user has `approval:decide` permission and is in approver lists
2. **Optimistic locking**: Uses `UPDATE WHERE status=pending` to prevent TOCTOU race conditions
3. **Update record**: Sets `status`, `decided_by`, `decided_at`, `decision_notes`
4. **Commit transaction**: Decision is persisted
5. **Emit audit event**: Dispatches `ApprovalDecidedEvent`
6. **Send signal**: Notifies workflow engine (best-effort, non-blocking)

**TOCTOU Protection:** The optimistic locking pattern ensures only one concurrent decision succeeds. If two users decide simultaneously, only the first `UPDATE` affects 1 row; the second affects 0 rows and raises `AlreadyDecidedError`.

### 3. Workflow Routing

Based on the decision, the workflow proceeds:

- **Approved path**: Workflow continues via the `approved` edge port
- **Rejected path**: Workflow continues via the `rejected` edge port (if configured)

```yaml
edges:
  - from: review_deployment
    to: execute_deployment
    from_port: approved
  - from: review_deployment
    to: log_rejection
    from_port: rejected
```

If no `rejected` edge exists, the workflow terminates when approval is rejected.

## Timeout Behavior

### Timeout Resolution (Three-Level Hierarchy)

The approval decision window (how long approvers have to respond) is resolved in this priority order:

**Resolution Order:**

1. **Per-node parameter** (`node.parameters.decision_window`): Highest priority
   - Set in workflow definition on individual approval nodes
   - Overrides all other settings
   - Example: `parameters: { decision_window: 3600 }` for 1-hour timeout

2. **Runtime setting** (`workflow_engine.approval_decision_window_seconds`): System-wide default
   - Configurable via settings catalog (Admin UI or API)
   - Applies to all approval nodes that don't specify their own timeout
   - Can be changed without modifying workflows

3. **Hardcoded fallback** (86400 seconds / 24 hours): Final fallback
   - Used only if runtime setting is not configured
   - Ensures approvals always have a timeout

The setting is defined in the settings catalog with key `workflow_engine.approval_decision_window_seconds`, default 86400, minimum 1 second.

### Timeout Field

The `timeout_at` field is set when the approval is created. It is a nullable, timezone-aware datetime that is indexed for efficient querying of expired approvals.

### Fallback Decision Routing

When an approval times out, the workflow engine uses the `fallback_decision` parameter to determine routing. The workflow engine:
1. Sets status to `expired`
2. Routes to `approved` or `rejected` edge based on `fallback_decision`
3. If `fallback_decision` is not set, the workflow terminates with failure

## Approver Configuration

### Three Authorization Modes

1. **Open (no approvers configured)**: Any user with `approval:decide` permission can approve
   - Both `approver_user_records` and `approver_group_records` are empty
   - Permission check via OPA (project-scoped or system-level)

2. **User-restricted**: Only specific users can approve
   - `approver_user_records` contains authorized user IDs
   - Current user's ID must be in the list
   - Permission check still required

3. **Group-restricted**: Only group members can approve
   - `approver_group_records` contains authorized group IDs
   - Current user must be a member of at least one group
   - Permission check still required

**Service principals** (cert-authenticated S2S callers) always bypass authorization checks for internal operations like cancellation.

### Junction Tables

Many-to-many relationships:
- `approval_approver_users`: `approval_requests` ↔ `users`
- `approval_approver_groups`: `approval_requests` ↔ `groups`

Both use `CASCADE` on delete, so removing a user/group also removes their approver associations.

### Approver Resolution

The workflow engine resolves approver usernames and group names to UUIDs before creating the approval:

```yaml
nodes:
  - id: review_deployment
    type: approval
    name: Review Deployment Plan
    parameters:
      approver_users: ["alice", "bob"]
      approver_groups: ["ops-team"]
```

At workflow execution time:
1. Usernames → User UUIDs (lookup via `users` table)
2. Group names → Group UUIDs (lookup via `groups` table)
3. UUIDs passed to approval creation API

The `ApprovalCreateRequest` receives:
- `approver_user_ids: list[UUID] | None`
- `approver_group_ids: list[UUID] | None`

## Workflow Integration

### V2 Workflow Format

Approvals are defined as nodes in V2 workflow definitions:

```yaml
nodes:
  - id: review_deployment
    type: approval
    name: Review Deployment Plan
    parameters: {}
    settings:
      timeout: 3600
```

**Node Parameters** (all optional):

| Parameter | Type | Default | Purpose |
|-----------|------|---------|---------|
| `credential_id` | str or None | None | Nexus credential UUID |
| `approver_users` | list[str] or None | None | Usernames who can approve (max 100) |
| `approver_groups` | list[str] or None | None | Group names whose members can approve (max 50) |
| `prompt` | str or None | None | Message to display to approvers |
| `fallback_decision` | "approve" or "reject" or None | None | Decision when approval times out |
| `decision_window` | int or None | None | Response timeout in seconds (≥1) |

**Node Settings** (optional):

- `timeout`: Activity timeout in seconds (workflow engine timeout, not decision window; minimum 1 second)
- `continue_on_failure`: Whether downstream nodes continue if approval fails
- `disabled`: Whether to skip this node entirely

### Routing via Edge Ports

Approval nodes have two output ports:
- `approved`: Path taken when decision is "approved"
- `rejected`: Path taken when decision is "rejected"

```yaml
edges:
  - from: review_deployment
    to: execute_deployment
    from_port: approved
  - from: review_deployment
    to: log_rejection
    from_port: rejected
```

**Important:** If no `rejected` edge exists and the approval is rejected, the workflow terminates.

### Workflow Context

The approval request includes three context structures for informed decision-making:

- **ActivitySummary**: Describes the next step (activity ID, name, and type) so approvers know what will execute after their decision.
- **WorkflowContext**: Captures the workflow version ID, workflow name, original input parameters, and the previous step context.
- **PreviousStepContext**: Records the preceding activity's ID, name, type, and output so approvers can see what already ran.

This context allows approvers to see:
- What workflow is running and its inputs
- What the previous step did and its output
- What will happen next if they approve or reject

## State Machine

An approval request transitions through these states:

```
         ┌─────────┐
         │ PENDING │ ◄─── Initial state (created)
         └────┬────┘
              │
              ├──────► APPROVED ──► (workflow continues on approved path)
              │
              ├──────► REJECTED ──► (workflow continues on rejected path)
              │
              ├──────► EXPIRED ───► (timeout, fallback_decision routing)
              │
              └──────► CANCELLED ─► (parent workflow cancelled)
```

The status values are: `pending`, `approved`, `rejected`, `expired`, and `cancelled` (as shown in the diagram above).

**Valid Transitions:**
- `PENDING` → `APPROVED` (user decides to approve)
- `PENDING` → `REJECTED` (user decides to reject)
- `PENDING` → `EXPIRED` (timeout reached with no decision)
- `PENDING` → `CANCELLED` (parent workflow cancelled)

**Terminal States:** All states except `PENDING` are terminal. Once an approval reaches a terminal state, it cannot be changed.

The service layer enforces this by checking that the current status is `PENDING` before allowing any transition, raising `ApprovalAlreadyDecidedError` otherwise.

## When to Use Approvals

### Use Cases

✅ **Use approvals for:**
- **Critical operations requiring human oversight** (e.g., production deployments, data deletion)
- **Compliance requirements** for manual approval before sensitive actions
- **Multi-stage workflows** where a human must review intermediate results
- **Gating automation** to prevent runaway processes

### Anti-Patterns

❌ **Avoid approvals for:**
- **High-frequency operations** (approvals are synchronous and block workflow progress)
- **Automated decision points** (use condition nodes instead)
- **Time-critical workflows** (timeouts can cause workflow failures)
- **Single-user workflows** (approval overhead without oversight benefit)

### Design Considerations

When designing approval workflows:

1. **Always configure a `rejected` edge** or the workflow will terminate on rejection
2. **Set appropriate `decision_window`** based on business requirements (default is 24 hours)
3. **Configure `fallback_decision`** to handle timeout cases gracefully
4. **Provide rich `workflow_context`** so approvers have enough information to decide
5. **Limit approver lists** to prevent authorization bottlenecks (max 1000 users or groups per list)
6. **Use project-scoped permissions** to ensure only relevant stakeholders can approve

Both approver lists (`approver_user_ids` and `approver_group_ids`) support up to 1000 entries each.

---

**Related Documentation:**

- [Approval API Specification](../../src/syntara/schemas/approvals/openapi.yaml)
- [Workflow Definition Guide](../workflow-engine/workflow-definition-guide.md)
- [Authorization Overview](../authorization.md)
- [Approval Authorization Model](./approval-authorization-model.md)
- [Approval Execution Pattern](./approval-execution-pattern.md)
