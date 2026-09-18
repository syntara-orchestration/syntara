# Execution Visualizer - Protocol & Data Spec

**Purpose**: Technical specification for real-time workflow execution visualization.

---

## Table of Contents

1. [Endpoints](#endpoints)
2. [Sequence: User Clicks "Run"](#sequence-user-clicks-run)
3. [Other Scenarios](#other-scenarios)
4. [WebSocket Messages](#websocket-messages)
5. [Data Structures](#data-structures)
6. [Visual Mapping](#visual-mapping)
7. [Implementation](#implementation)
8. [Update Flow](#update-flow)
9. [Protocol Rules](#protocol-rules)
10. [Step State Inference (Client-Side)](#step-state-inference-client-side)

---

## Endpoints

```
POST /api/v1/executions
WS   /ws/workflows/v1/executions/{execution_id}?replay={event_id}
GET  /api/v1/executions/{execution_id}?include=workflow_definition,activities
```

---

## Sequence: User Clicks "Run"

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: User Action                                             │
└─────────────────────────────────────────────────────────────────┘
  User clicks "Run workflow" button on builder page
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: HTTP POST - Create Execution                            │
└─────────────────────────────────────────────────────────────────┘
  POST /api/v1/executions
  Body: { "workflow_id": "wf-789", "input_data": {} }
  ↓
  Response: {
    "id": "exec-123-456",
    "workflow_id": "wf-789",
    "workflow_version_id": "ver-001",
    "status": "pending",
    "created_at": "2025-01-20T10:00:00Z",
    "started_at": null,
    "completed_at": null
  }
  ↓
  UI: Store execution_id from response.id, switch to runtime mode
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: WebSocket Connect                                       │
└─────────────────────────────────────────────────────────────────┘
  WS /ws/workflows/v1/executions/exec-123-456?replay=0
  ↓
  Connection established
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Receive Initial Snapshot                                │
└─────────────────────────────────────────────────────────────────┘
  Message Type: initial_snapshot
  {
    "type": "initial_snapshot",
    "execution_id": "exec-123-456",
    "event_id": "1737307800000-0",
    "execution": {
      "id": "exec-123-456",
      "workflow_id": "wf-789",
      "workflow_version_id": "ver-001",
      "status": "running",
      "created_at": "2025-01-20T10:00:00Z",
      "started_at": "2025-01-20T10:00:01Z",
      "completed_at": null,
      "activities": [
        { "activity_id": "manual_trigger", "status": "pending", "error_details": null, "started_at": null, "completed_at": null },
        { "activity_id": "agent_task_1", "status": "pending", "error_details": null, "started_at": null, "completed_at": null }
      ]
    },
    "timestamp": "2025-01-20T10:00:01Z"
  }
  ↓
  UI: Initialize activityStates Map, render all canvas steps as "pending"
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Real-Time Activity Patches                              │
└─────────────────────────────────────────────────────────────────┘
  Message Type: activity_patch (trigger starts)
  {
    "type": "activity_patch",
    "execution_id": "exec-123-456",
    "event_id": "1737307801000-0",
    "ops": [
      { "op": "replace", "path": "/activities/manual_trigger/status", "value": "running" }
    ],
    "timestamp": "2025-01-20T10:00:02Z"
  }
  ↓
  UI: Update Map, step border → blue, badge → spinner
  ↓
  Message Type: activity_patch (trigger completes, agent starts)
  {
    "type": "activity_patch",
    "execution_id": "exec-123-456",
    "event_id": "1737307802000-0",
    "ops": [
      { "op": "replace", "path": "/activities/manual_trigger/status", "value": "completed" },
      { "op": "replace", "path": "/activities/agent_task_1/status", "value": "running" }
    ],
    "timestamp": "2025-01-20T10:00:05Z"
  }
  ↓
  UI: Update Map
    - manual_trigger: border → green, badge → checkmark
    - edge trigger→agent: dotted → solid
    - agent_task_1: border → blue, badge → spinner
  ↓
  ... more activity_patch messages as workflow executes ...
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Receive Final Snapshot                                  │
└─────────────────────────────────────────────────────────────────┘
  Message Type: final_snapshot
  {
    "type": "final_snapshot",
    "execution_id": "exec-123-456",
    "event_id": "1737307850000-0",
    "execution": {
      "id": "exec-123-456",
      "workflow_id": "wf-789",
      "workflow_version_id": "ver-001",
      "status": "completed",
      "created_at": "2025-01-20T10:00:00Z",
      "started_at": "2025-01-20T10:00:01Z",
      "completed_at": "2025-01-20T10:05:30Z",
      "activities": [
        { "activity_id": "manual_trigger", "status": "completed", "error_details": null, "started_at": "2025-01-20T10:00:01Z", "completed_at": "2025-01-20T10:00:05Z" },
        { "activity_id": "agent_task_1", "status": "completed", "error_details": null, "started_at": "2025-01-20T10:00:05Z", "completed_at": "2025-01-20T10:05:30Z" }
      ]
    },
    "timestamp": "2025-01-20T10:05:30Z"
  }
  ↓
  UI: Set final states, show "Completed" status
  ↓
  WebSocket connection CLOSED by server
```

---

## Other Scenarios

### Historical Execution

```
GET /api/v1/executions/exec-123?include=workflow_definition,activities
→ Returns: workflow structure + final activity states
→ NO WebSocket connection needed
```

### Reconnection (After Disconnect)

```
WS /ws/workflows/v1/executions/exec-123?replay={lastEventId}
→ Receive: Missed events since lastEventId
→ Continue receiving live stream
```

---

## WebSocket Messages

### Message Types

| Type               | When                       | Purpose                         |
| ------------------ | -------------------------- | ------------------------------- |
| `initial_snapshot` | On connect with `replay=0` | Set initial activity states     |
| `activity_patch`   | On every status change     | Update specific activity fields |
| `final_snapshot`   | Execution complete         | Final state before disconnect   |

### 1. Initial Snapshot

```json
{
  "type": "initial_snapshot",
  "execution_id": "exec-123-456",
  "event_id": "1737307800000-0",
  "execution": {
    "id": "exec-123-456",
    "workflow_id": "wf-789",
    "workflow_version_id": "ver-001",
    "status": "running",
    "created_at": "2025-01-20T10:00:00Z",
    "started_at": "2025-01-20T10:00:01Z",
    "completed_at": null,
    "activities": [
      {
        "activity_id": "trigger",
        "status": "pending",
        "error_details": null,
        "started_at": null,
        "completed_at": null
      },
      { "activity_id": "agent", "status": "pending", "error_details": null, "started_at": null, "completed_at": null }
    ]
  },
  "timestamp": "2025-01-20T10:00:01Z"
}
```

**Action**: Initialize `Map<activity_id, ActivityState>`

### 2. Activity Patch (JSON Patch RFC 6902)

```json
{
  "type": "activity_patch",
  "execution_id": "exec-123-456",
  "event_id": "1737307801000-0",
  "ops": [
    {
      "op": "replace",
      "path": "/activities/trigger/status",
      "value": "running"
    }
  ],
  "timestamp": "2025-01-20T10:00:02Z"
}
```

**Action**: Parse path → Update Map

**Path Format**: `/activities/{activity_id}/{field}`

**Fields**:

- `status` → `"pending" | "running" | "completed" | "failed" | "skipped" | "cancelled" | "retrying"`
- `error_details` → `string`
- `started_at` → `ISO8601 timestamp`
- `completed_at` → `ISO8601 timestamp`

### 3. Final Snapshot

```json
{
  "type": "final_snapshot",
  "execution_id": "exec-123-456",
  "event_id": "1737307850000-0",
  "execution": {
    "id": "exec-123-456",
    "workflow_id": "wf-789",
    "workflow_version_id": "ver-001",
    "status": "completed",
    "created_at": "2025-01-20T10:00:00Z",
    "started_at": "2025-01-20T10:00:01Z",
    "completed_at": "2025-01-20T10:05:30Z",
    "activities": [
      {
        "activity_id": "trigger",
        "status": "completed",
        "error_details": null,
        "started_at": "2025-01-20T10:00:01Z",
        "completed_at": "2025-01-20T10:00:05Z"
      },
      {
        "activity_id": "agent",
        "status": "completed",
        "error_details": null,
        "started_at": "2025-01-20T10:00:05Z",
        "completed_at": "2025-01-20T10:05:30Z"
      }
    ]
  },
  "timestamp": "2025-01-20T10:05:30Z"
}
```

**Action**: Set final states → Connection closes

---

## Data Structures

### TypeScript Types

```typescript
// WebSocket message types
interface JsonPatchOp {
  op: 'add' | 'remove' | 'replace' | 'move' | 'copy' | 'test'
  path: string // e.g., "/activities/fetch_data/status"
  value?: unknown
  from?: string
}

interface ActivityData {
  activity_id: string
  status: string
  error_details: string | null
  started_at: string | null
  completed_at: string | null
}

interface Execution {
  id: string // REST API uses 'id' from BaseResource
  workflow_id: string
  workflow_version_id: string
  status: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  error: string | null // Mirrors ExecutionRead.error: same value as error_details when
  // status is 'failed' or 'completed_with_errors', null otherwise
  // (even if error_details is stale from a prior state)
  activities: ActivityData[]
}

interface ExecutionSnapshotMessage {
  type: 'initial_snapshot' | 'final_snapshot'
  execution_id: string
  event_id: string
  execution: Execution
  timestamp: string
}

interface ActivityPatchMessage {
  type: 'activity_patch'
  execution_id: string
  event_id: string
  ops: JsonPatchOp[]
  timestamp: string
}

type WebSocketMessage = ExecutionSnapshotMessage | ActivityPatchMessage
```

### Zustand Store

```typescript
interface ExecutionStore {
  // State
  activityStates: Map<string, ActivityState> // Keyed by activity_id
  lastEventId: string
  isConnected: boolean

  // Actions
  applyPatch(ops: JsonPatchOp[]): void
  setInitialState(activities: ActivityData[]): void
}

// Internal ActivityState type (camelCase fields)
interface ActivityState {
  activityId: string // The activity identifier
  status: ActivityStatus // 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled'
  errorDetails?: string | null // Error message if failed
  startedAt?: string | null // ISO8601 timestamp
  completedAt?: string | null // ISO8601 timestamp
}

// Note: API uses snake_case (error_details, started_at, completed_at)
// Internal types use camelCase (errorDetails, startedAt, completedAt)
// The store transforms snake_case → camelCase when processing messages
```

**Field Name Mapping:**

| API Field (snake_case) | Internal Field (camelCase) | Type             |
| ---------------------- | -------------------------- | ---------------- |
| `activity_id`          | `activityId`               | `string`         |
| `status`               | `status`                   | `ActivityStatus` |
| `error_details`        | `errorDetails`             | `string \| null` |
| `started_at`           | `startedAt`                | `string \| null` |
| `completed_at`         | `completedAt`              | `string \| null` |

### React Flow graph vertices (`nodes[]`)

```typescript
const nodes = activities.map((activity) => ({
  id: activity.id,
  data: {
    // Static
    name: activity.name,
    type: activity.type,

    // Dynamic - updates from Map
    activityState: activityStates.get(activity.id),
  },
}))
```

### Edge Status (Client-Side Derived)

Edge status is derived based on the type of edge (see Step State Inference section for details):

```typescript
// Simplified - actual implementation handles multiple edge types
function determineEdgeStatus(edge, activityStates) {
  // Trigger edges: passed when target started
  if (edge.source.startsWith('trigger-')) {
    const targetState = activityStates.get(edge.target)
    return targetState?.status !== 'pending' ? 'passed' : 'pending'
  }

  // Branching edges (true/false/done/loop): passed when target started
  if (isBranchHandle(edge.sourceHandle)) {
    const targetState = activityStates.get(edge.target)
    return targetState?.status !== 'pending' ? 'passed' : 'pending'
  }

  // Regular edges: passed when source reaches a terminal status
  const sourceState = activityStates.get(edge.source)
  return ['completed', 'failed', 'cancelled'].includes(sourceState?.status ?? '') ? 'passed' : 'pending'
}
```

---

## Visual Mapping

**Step Status Colors** (theme-agnostic hex values):

| Status      | Border           | Badge   | Animation | Style      |
| ----------- | ---------------- | ------- | --------- | ---------- |
| `pending`   | `#6B7280` Gray   | `[...]` | None      | Solid      |
| `running`   | `#3B82F6` Blue   | `[⟳]`   | Spin      | Solid      |
| `completed` | `#10B981` Green  | `[✓]`   | None      | Solid      |
| `failed`    | `#EF4444` Red    | `[!]`   | Pulse     | Solid      |
| `skipped`   | `#9CA3AF` Gray   | None    | None      | **Dashed** |
| `cancelled` | `#F97316` Orange | `[⊘]`   | None      | Solid      |

_Note: Colors are theme-agnostic and should work on both light and dark backgrounds. Implementation may need to adjust opacity or add contrast enhancements based on theme._

**Edge Visual**:

- Source `pending/running` → Dotted line
- Source `completed/failed/cancelled` → Solid line

_Note: Edge color should adapt to theme (e.g., white/light gray for dark theme, dark gray for light theme)._

---

## Implementation

### Apply JSON Patch

```typescript
function applyPatch(ops: JsonPatchOp[]) {
  for (const op of ops) {
    if (op.op === 'replace' || op.op === 'add') {
      const [, activityId, field] = op.path.match(/^\/activities\/([^/]+)\/(.+)$/)

      activityStates.set(activityId, {
        ...activityStates.get(activityId),
        [field]: op.value,
      })
    }
  }
}
```

### Handle Messages

```typescript
function handleMessage(msg: WebSocketMessage) {
  switch (msg.type) {
    case 'initial_snapshot':
      msg.execution.activities.forEach((a) =>
        activityStates.set(a.activity_id, {
          status: a.status,
          error_details: a.error_details,
          started_at: a.started_at,
          completed_at: a.completed_at,
        })
      )
      lastEventId = msg.event_id
      break

    case 'activity_patch':
      applyPatch(msg.ops)
      lastEventId = msg.event_id
      break

    case 'final_snapshot':
      // Set final states, connection will close
      msg.execution.activities.forEach((a) =>
        activityStates.set(a.activity_id, {
          status: a.status,
          error_details: a.error_details,
          started_at: a.started_at,
          completed_at: a.completed_at,
        })
      )
      lastEventId = msg.event_id
      break
  }
}
```

### Reconnect

```typescript
// Store event_id on every message
let lastEventId = '0'

// On disconnect
connectWebSocket(executionId, lastEventId)
// → WS /ws/workflows/v1/executions/{execution_id}?replay={lastEventId}
```

---

## Update Flow

```
WebSocket Message
  ↓
Parse JSON Patch (path → activityName, field)
  ↓
Update Map: activityStates.set(name, { ...prev, [field]: value })
  ↓
Zustand triggers React re-render
  ↓
React Flow `nodes` receive new `data.activityState`
  ↓
Steps re-render with new border/badge
```

---

## Protocol Rules

1. **Always store `event_id`** from every message (for reconnection)
2. **Backend does NOT send edge status** (derive it client-side from step states and edge type)
3. **No extra GET for live run** (workflow already in Zustand)
4. **WebSocket closes after `final_snapshot`**
5. **Reconnect with `?replay={lastEventId}`** to catch up

---

## Step State Inference (Client-Side)

The backend only sends status for executable activities (tasks, agent_task, etc.). Structural steps (loops, conditions, converge) do **not** have direct backend state. The client infers their visual state from connected activities.

### Inference System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                     STEP STATE INFERENCE SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   WebSocket Message                   Workflow Graph                         │
│   ═══════════════════                 ═══════════════                        │
│   { activity_id: "task1",             [Trigger] → [Loop] → [Task1] → ...    │
│     status: "completed" }                  │         │                       │
│                                            ▼         ▼                       │
│                                       has backend  inferred from             │
│                                       state        downstream steps          │
│                                                                              │
│   ExecutionStateEnricher                                                     │
│   ══════════════════════                                                     │
│   1. Apply direct backend states                                             │
│   2. Infer trigger state (first activity started → trigger completed)        │
│   3. Infer structural step states via type-specific inferrers               │
│   4. Calculate edge statuses                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step type inferrers (structural activities)

| Step / activity type | Inferrer class                       | Logic                                                                |
| -------------------- | ------------------------------------ | -------------------------------------------------------------------- |
| **Loop**             | `LoopNodeStateInferrer`              | Checks 'done' and 'loop' edges; completed when 'done' target started |
| **Condition**        | `ConditionalNodeStateInferrer`       | Completed when any branch target has started                         |
| **Approval**         | `ConditionalNodeStateInferrer`       | Same logic as condition (has approved/rejected branches)             |
| **Converge**         | `ConvergeNodeStateInferrer`          | Completed when the converge step's own `startedAt` is set            |
| **Trigger**          | Built-in to `ExecutionStateEnricher` | Completed when any downstream activity has started                   |

### Inference Examples

**Loop step:**

```typescript
// Loop is "completed" when execution exits the loop
// (i.e., when the 'done' edge target has started)

// Edges: loop → body (handle: 'loop'), loop → next (handle: 'done')
// If 'next' step has startedAt → loop is completed
// If 'body' step has startedAt but 'next' hasn't → loop is running
```

**Condition step:**

```typescript
// Condition is "completed" when a branch was taken
// (i.e., when any 'true' or 'false' edge target has started)

// Edges: condition → taskA (handle: 'true'), condition → taskB (handle: 'false')
// If taskA.startedAt OR taskB.startedAt → condition is completed
```

### Skip Detection (Traversal Algorithm)

Steps can be marked as "skipped" when they're on a branch that wasn't taken:

```typescript
// WorkflowTraversal.shouldMarkAsSkipped(nodeId, activities, edges, activityStates)
//
// Returns true if:
// 1. Step is on a non-taken branch of a completed condition
// 2. Step is downstream from a skipped step
// 3. Step has no downstream pending steps (cascade complete)
```

**Implementation location:** `packages/syntara-ui/src/routes/builder/utils/executionState/traversal.ts`

### Edge Status Determination

Edge visual status is derived from step states:

```typescript
// Edge is "passed" (solid line) when:
// - For branching edges (from condition/approval): target step has started
// - For converge outgoing edges: target step has started
// - For trigger edges: target step has started
// - For regular edges: source reached a terminal status (completed/failed/cancelled)

// Edge is "pending" (dotted line) otherwise
```

**Implementation location:** `packages/syntara-ui/src/routes/builder/utils/executionState/ExecutionStateEnricher.ts`

---
