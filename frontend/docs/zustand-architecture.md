# Workflow State Management

> **TL;DR:** We use Zustand to manage workflow state in the builder. The data flows from the backend API → Zustand store → React components. Use custom hooks to read state, `useWorkflowStoreActions()` to dispatch actions.

---

## Table of Contents

1. [The Big Picture](#the-big-picture)
2. [How Data Flows](#how-data-flows)
3. [Store Architecture](#store-architecture)
4. [Using the Store](#using-the-store)
5. [Common Pitfalls & Solutions](#common-pitfalls-solutions)
6. [Testing Components with Store](#testing-components-with-store)

---

## The Big Picture

When a user opens a workflow in the builder, here's what happens:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW                                          │
└──────────────────────────────────────────────────────────────────────────────┘

  ┌─────────┐      ┌──────────────┐      ┌─────────────────┐      ┌──────────┐
  │ Backend │ ──▶  │ TanStack     │ ──▶  │ Zustand Store   │ ──▶  │ React    │
  │   API   │      │ Query        │      │ (Client State)  │      │ UI       │
  └─────────┘      └──────────────┘      └─────────────────┘      └──────────┘
       │                  │                      │                      │
       │           Fetches & caches        Holds workflow          Renders &
       │           server data             during editing          responds to
       │                                                           user actions
       │                                         │                      │
       │                                         ▼                      │
       │                                  ┌─────────────┐               │
       │                                  │  Factory    │◀──────────────┘
       │                                  │  Functions  │   Creates new
       │                                  └─────────────┘   triggers/activities
       │                                         │
       └─────────────────────────────────────────┘
                    Saves workflow back to API
```

### Why Two State Systems?

| System             | Purpose                                 | Example                                    |
| ------------------ | --------------------------------------- | ------------------------------------------ |
| **TanStack Query** | Server state (what's on the backend)    | List of all workflows, execution history   |
| **Zustand Store**  | Client state (what the user is editing) | The workflow currently open in the builder |

This separation is intentional:

- **TanStack Query** handles caching, refetching, and sync with the server
- **Zustand** provides fast, local state for the interactive builder experience

---

## How Data Flows

### 1. Loading a Workflow

```text
User clicks "Edit Workflow"
         │
         ▼
┌─────────────────────────────────┐
│  TanStack Query fetches from    │
│  GET /api/v1/workflows/{workflow_id} │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  BuilderContent calls           │
│  loadWorkflow(activities)       │
│  (pure function — returns       │
│   { activities, edges })        │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  BuilderContent calls           │
│  loadWorkflowWithEdges(         │
│    flatWorkflow, edges)         │
│  (atomic store update)          │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Zustand store updates:         │
│  • currentWorkflow = {...}      │
│  • workflowVersion++            │
│  • edges = generatedEdges       │
│  • isDirty = false              │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Components re-render with      │
│  new workflow data              │
└─────────────────────────────────┘
```

### 2. User Makes an Edit

```text
User drags a new task onto canvas
         │
         ▼
┌─────────────────────────────────┐
│  Component calls action:        │
│  addActivity(newTask)           │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Zustand updates activities     │
│  array (immutably)              │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  ONLY subscribed components     │  ← This is key!
│  re-render (not the whole app)  │
└─────────────────────────────────┘
```

### 3. Saving Changes

```text
User clicks "Save"
         │
         ▼
┌─────────────────────────────────┐
│  Read current state:            │
│  useWorkflowStore.getState()    │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  TanStack Query mutation:       │
│  PATCH /api/v1/workflows/{workflow_id} │
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│  Invalidate cache, refetch      │
│  to sync with server            │
└─────────────────────────────────┘
```

---

## Store Architecture

### File Structure

```text
packages/syntara-ui/src/stores/
├── useWorkflowStore.ts          # Main workflow store (with Zundo undo/redo)
├── workflowStoreSelectors.ts    # Exported selectors
├── workflowStoreTypes.ts        # Store type definitions
├── workflowActivityHelpers.ts   # Activity manipulation helpers
├── workflowFactories.ts         # Entity factory functions
├── useAuthStore.ts              # Authentication state (tokens, session, refresh)
├── useProjectStore.ts           # Active project scoping
# Note: WebSocket store is in lib/websocket/store.ts
# Note: Execution store is in routes/workflows/stores/useExecutionStore.ts
```

### State Shape

```typescript
interface WorkflowStore {
  // State
  currentWorkflow: WorkflowDefinition | null
  workflowVersion: number // Increments only on setWorkflow()
  edges: EdgeConnection[]
  isDirty: boolean // Tracks unsaved changes

  // Workflow loading/unloading
  setWorkflow: (workflow: WorkflowDefinition | null) => void
  loadWorkflowWithEdges: (workflow: WorkflowDefinition, edges: EdgeConnection[]) => void
  updateWorkflow: (updater: (workflow) => workflow) => void

  // Dirty state management
  markClean: () => void // Called after successful save
  markDirty: () => void // Called when metadata changes

  // Edge management
  setEdges: (edges: EdgeConnection[]) => void

  // Trigger management
  addTrigger: (trigger: Trigger) => void
  removeTrigger: (index: number) => void
  updateTrigger: (index: number, trigger: Trigger) => void

  // Activity management
  addActivity: (activity: Activity) => void
  removeActivity: (activityId: string) => void
  updateActivity: (activityId: string, updates: Partial<Activity>) => void
  moveActivityBefore: (activityId: string, beforeActivityId: string) => void
  moveActivityAfter: (activityId: string, afterActivityId: string) => void
  reorderActivitiesFromEdges: () => void

  // Converge branches (join steps) — keeps `converge.branches` in sync with edges
  syncConvergeNodeBranches: () => void

  // Atomic batch operations
  batchRemoveNodesAndEdges: (params: BatchRemoveParams) => void
  batchAddActivitiesAndEdges: (params: BatchAddParams) => void
}
```

**Undo/Redo Support:** The workflow store wraps Zustand with [Zundo](https://github.com/charkour/zundo) temporal middleware, providing `undo()` and `redo()` actions. The temporal store tracks activity and edge changes, enabling users to undo/redo edits on the builder canvas.

### Visual Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           useWorkflowStore                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   STATE                        ACTIONS                                       │
│   ─────                        ───────                                       │
│   currentWorkflow              setWorkflow()              Load/clear         │
│   workflowVersion              loadWorkflowWithEdges()    Atomic load        │
│   edges                        updateWorkflow()           Incremental update │
│   isDirty                                                                    │
│                                setEdges()                 Update connections │
│                                markClean()                Clear dirty flag   │
│                                markDirty()                Set dirty flag     │
│                                                                              │
│                                addActivity()              Add step           │
│                                removeActivity()           Delete step        │
│                                updateActivity()           Modify step        │
│                                moveActivityBefore()       Reorder steps    │
│                                moveActivityAfter()        Reorder steps    │
│                                reorderActivitiesFromEdges() Topology sort    │
│                                                                              │
│                                addTrigger()               Add trigger        │
│                                removeTrigger()            Delete trigger     │
│                                updateTrigger()            Modify trigger     │
│                                                                              │
│                                syncConvergeNodeBranches()  Sync converge     │
│                                batchRemoveNodesAndEdges() Atomic delete      │
│                                batchAddActivitiesAndEdges() Atomic add       │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ACCESS PATTERNS                                                            │
│   ───────────────                                                            │
│                                                                              │
│   useActivities()              Read activities (selective subscription)      │
│   useEdges()                   Read edges (selective subscription)           │
│   useWorkflowStoreActions()    Get actions (no subscription)                 │
│   useWorkflowStore(selector)   Custom selection (advanced)                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         workflowFactories.ts                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│   createManualTrigger()        createScriptActivity()                        │
│   createScheduledTrigger()     createApiActivity()                           │
│   createEventTrigger()         createAgenticActivity()                       │
│                                createConditionActivity()                     │
│                                createLoopActivity()                          │
│                                createConvergeActivity()                      │
│                                createConnectorActivity()                     │
│                                createAAPJobTemplateActivity()                │
│                                createGenericActivity()                       │
│                                createApprovalActivity()                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Using the Store

### 1. Reading State → Custom Hooks (Recommended)

Custom hooks provide the cleanest API for reading state:

```typescript
import { useActivities, useWorkflowName, useHasWorkflow } from '../../stores/useWorkflowStore'

function WorkflowHeader() {
  const name = useWorkflowName() // Only re-renders when name changes
  const hasWorkflow = useHasWorkflow() // Only re-renders when workflow loads/unloads

  if (!hasWorkflow) return <EmptyState />
  return <h1>{name}</h1>
}
```

**Available hooks:**

| Hook                   | Returns              | Re-renders when...               |
| ---------------------- | -------------------- | -------------------------------- |
| `useCurrentWorkflow()` | Full workflow object | Any workflow field changes       |
| `useWorkflowVersion()` | Number               | New workflow loaded              |
| `useActivities()`      | Activity[]           | Activities added/removed/updated |
| `useTriggers()`        | Trigger[]            | Triggers added/removed/updated   |
| `useEdges()`           | Edge[]               | Connections change               |
| `useWorkflowName()`    | String               | Name changes                     |
| `useActivitiesCount()` | Number               | Activity count changes           |
| `useTriggersCount()`   | Number               | Trigger count changes            |
| `useIsDirty()`         | Boolean              | Dirty state changes              |
| `useHasWorkflow()`     | Boolean              | Workflow loaded/unloaded         |

### 2. Dispatching Actions → Action Accessor

When you only need to dispatch actions (not read state), use `useWorkflowStoreActions()`:

```typescript
import { useWorkflowStoreActions } from '../../stores/useWorkflowStore'

function DeleteButton({ nodeId }: { nodeId: string }) {
  // ✅ Component won't re-render when store changes!
  const { removeActivity } = useWorkflowStoreActions()

  return <button onClick={() => removeActivity(nodeId)}>Delete</button>
}
```

**Why this pattern?**

```typescript
// ❌ BAD: Component re-renders on ANY store change
const removeActivity = useWorkflowStore((state) => state.removeActivity)

// ✅ GOOD: Component never re-renders from store changes
const { removeActivity } = useWorkflowStoreActions()
```

### 3. Typed Selectors (Advanced)

For custom selections or combining multiple pieces of state:

```typescript
import { useWorkflowStore, selectActivities } from '../../stores/useWorkflowStore'

function MyComponent() {
  // Use pre-defined selector
  const activities = useWorkflowStore(selectActivities)

  // Or create inline selector for complex cases
  const taskCount = useWorkflowStore(
    (state) => state.currentWorkflow?.workflow.activities.filter((a) => a.type === 'task').length ?? 0
  )
}
```

### 4. Direct State Access (Outside React)

For non-React code or callbacks:

```typescript
// Read state synchronously
const workflow = useWorkflowStore.getState().currentWorkflow

// Call actions directly
useWorkflowStore.getState().addActivity(newActivity)

// Subscribe to changes
const unsubscribe = useWorkflowStore.subscribe((state) => {
  console.log('State changed:', state)
})
```

### 5. Creating Entities → Factory Functions

```typescript
import { createScriptActivity, createManualTrigger } from '../../stores/workflowFactories'

// Clean, type-safe entity creation
const task = createScriptActivity('task-1', 'Run Script', 'python', 'print("hello")')
const trigger = createManualTrigger(true) // requiresApproval = true
```

---

## Why This Architecture?

### Benefit 1: Performance by Default

Components only re-render when their specific data changes:

```typescript
function StepCount() {
  const count = useActivitiesCount() // Re-renders: only when count changes
  return <span>{count} steps</span> // NOT when step names/positions change
}
```

### Benefit 2: Simple Mental Model

| Need to...      | Do this                         |
| --------------- | ------------------------------- |
| Read state      | Use a custom hook               |
| Dispatch action | Use `useWorkflowStoreActions()` |
| Create entity   | Use a factory function          |

No decisions about selectors, memoization, or subscription patterns—it's built in.

### Benefit 3: Atomic Updates

Workflow state has interdependencies. Deleting a step (activity) must also update edges and converge branches. We handle this atomically:

```typescript
// ✅ All changes happen together, one re-render
batchRemoveNodesAndEdges({
  nodeIds: ['node-1', 'node-2'],
  edges: updatedEdges,
})
```

### Benefit 4: Easy Testing

```typescript
// Reset state before each test
beforeEach(() => {
  useWorkflowStore.setState({
    currentWorkflow: null,
    workflowVersion: 0,
    edges: [],
  })
})

// Test actions directly
it('adds activity', () => {
  useWorkflowStore.getState().setWorkflow(mockWorkflow)
  useWorkflowStore.getState().addActivity(mockTask)
  expect(useWorkflowStore.getState().currentWorkflow.workflow.activities).toHaveLength(1)
})
```

---

## Common Pitfalls & Solutions

This architecture addresses the most common failure modes in workflow builder state:

### Pitfall 1: Accidental Broad Subscriptions

```typescript
// ❌ BAD: Re-renders on ANY state change
function MyComponent() {
  const store = useWorkflowStore() // Subscribes to entire store!
  return <div>{store.currentWorkflow?.name}</div>
}

// ✅ GOOD: Re-renders only when name changes
function MyComponent() {
  const name = useWorkflowName()
  return <div>{name}</div>
}
```

### Pitfall 2: Inline Selectors Creating New Objects

```typescript
// ❌ BAD: Creates new object every render, breaks memoization
const data = useWorkflowStore((state) => ({
  version: state.workflowVersion,
  name: state.currentWorkflow?.name,
}))

// ✅ GOOD: Use separate hooks
const version = useWorkflowVersion()
const name = useWorkflowName()

// ✅ GOOD: Or use shallow comparison for objects
import { useShallow } from 'zustand/react/shallow'
const data = useWorkflowStore(
  useShallow((state) => ({
    version: state.workflowVersion,
    name: state.currentWorkflow?.name,
  }))
)
```

### Pitfall 3: Non-Atomic Coupled Updates

```typescript
// ❌ BAD: Two separate updates, inconsistent intermediate state
removeActivity(nodeId)
setEdges(filteredEdges) // Components might render between these calls!

// ✅ GOOD: Single atomic update
batchRemoveNodesAndEdges({
  nodeIds: [nodeId],
  edges: filteredEdges,
})
```

---

## Why One Store?

The workflow domain has **inherent interdependencies** that cannot be decoupled:

```text
edges ←──references──► activities
  │                        │
  │                        ▼
  │               converge.branches
  │                        │
  └────────────────────────┘
        (must stay in sync)
```

### The Tight Coupling Problem

1. **Edges reference activities** - An edge's `source` and `target` are activity IDs
2. **Converge (join) steps depend on edges** - `converge.branches` is computed from incoming edges
3. **Parallel containers are auto-generated** - Created based on edge patterns
4. **Activity ordering depends on edges** - Topological sort uses edge connections
5. **Deletion cascades** - Removing an activity must update edges AND converge branches

This isn't a UI design choice—it reflects the **actual workflow execution model** in the backend.

### Problem with Multiple Stores

```typescript
// ❌ RISKY: These updates are coupled but notify subscribers separately
function deleteNode(nodeId: string) {
  useActivitiesStore.getState().removeActivity(nodeId)
  // Subscribers see inconsistent state here!
  useEdgesStore.getState().removeEdgesForNode(nodeId)
}
```

### Solution: Single Store with Atomic Operations

```typescript
// ✅ CORRECT: All changes happen atomically
batchRemoveNodesAndEdges({
  nodeIds: ['node-1'],
  edges: filteredEdges,
})
// Single state update, single re-render, consistent state
```

**One store = one transaction boundary = consistent state.**

---

## Advanced Patterns

### Tracking Unsaved Changes (Dirty State)

The store tracks whether there are unsaved changes using the `isDirty` flag:

```typescript
// Check if there are unsaved changes
const isDirty = useIsDirty()

// Show warning before navigation
if (isDirty) {
  const confirmed = confirm('You have unsaved changes. Are you sure you want to leave?')
  if (!confirmed) return
}
```

**When isDirty is set:**

- Automatically set when activities/edges are modified
- When metadata is updated (via `markDirty()`)

**When isDirty is cleared:**

- After successful save (via `markClean()`)
- When loading a new workflow (via `setWorkflow()`)

```typescript
// After saving successfully
const handleSave = async () => {
  const workflow = useWorkflowStore.getState().currentWorkflow
  await saveWorkflow(workflow)
  useWorkflowStore.getState().markClean() // Clear dirty flag
}

// When metadata changes (name, description)
const handleNameChange = (name: string) => {
  useWorkflowStore.getState().updateWorkflow((w) => ({ ...w, name }))
  useWorkflowStore.getState().markDirty() // Mark as dirty
}
```

### Atomic Workflow Loading

Use `loadWorkflowWithEdges()` to load a workflow and its edges atomically:

```typescript
// ✅ GOOD: Atomic operation - single state update
const { workflow, edges } = loadAndFlattenWorkflow(apiResponse)
useWorkflowStore.getState().loadWorkflowWithEdges(workflow, edges)

// ❌ BAD: Two separate updates - components might render between calls
useWorkflowStore.getState().setWorkflow(workflow)
useWorkflowStore.getState().setEdges(edges) // Components see inconsistent state!
```

**Why atomic loading matters:**

- Prevents race conditions where components see workflow without edges
- Single re-render instead of two
- Ensures edges always match the workflow

### Applying Incremental Updates

Use `setWorkflow()` vs `updateWorkflow()` appropriately:

```typescript
// setWorkflow: New workflow loaded, increments workflowVersion
useWorkflowStore.getState().setWorkflow(newWorkflow)

// updateWorkflow: Modify existing workflow, keeps same workflowVersion
useWorkflowStore.getState().updateWorkflow((workflow) => ({
  ...workflow,
  name: `${workflow.name} (updated)`,
}))
```

### Subscribing Outside React

```typescript
// For debugging or external integrations
const unsubscribe = useWorkflowStore.subscribe((state, prevState) => {
  if (state.workflowVersion !== prevState.workflowVersion) {
    console.log('New workflow loaded!')
  }
})
```

### Testing Components with Store

```typescript
// Mock the store in component tests
vi.mock('../../stores/useWorkflowStore', () => ({
  useWorkflowStore: vi.fn((selector) => selector(mockState)),
  useWorkflowStoreActions: vi.fn(() => ({
    updateActivity: mockUpdateActivity,
  })),
  selectCurrentWorkflow: (state) => state.currentWorkflow,
}))
```

---

## Migration Guide

### From Inline Selectors to Custom Hooks

```typescript
// Before
const version = useWorkflowStore((state) => state.workflowVersion)
const activities = useWorkflowStore((state) => state.currentWorkflow?.workflow.activities)

// After
const version = useWorkflowVersion()
const activities = useActivities()
```

### From Direct Action Subscription to Action Accessor

```typescript
// Before (component re-renders on any state change)
const updateActivity = useWorkflowStore((state) => state.updateActivity)

// After (component doesn't re-render on state changes)
const { updateActivity } = useWorkflowStoreActions()
```

---

## Quick Reference

| I want to...               | Import                    | Use                                                             |
| -------------------------- | ------------------------- | --------------------------------------------------------------- |
| Read activities            | `useActivities`           | `const activities = useActivities()`                            |
| Read edges                 | `useEdges`                | `const edges = useEdges()`                                      |
| Check for unsaved changes  | `useIsDirty`              | `const isDirty = useIsDirty()`                                  |
| Check if workflow loaded   | `useHasWorkflow`          | `const loaded = useHasWorkflow()`                               |
| Load workflow atomically   | `useWorkflowStoreActions` | `const { loadWorkflowWithEdges } = useWorkflowStoreActions()`   |
| Update a step (activity)   | `useWorkflowStoreActions` | `const { updateActivity } = useWorkflowStoreActions()`          |
| Delete steps atomically    | `useWorkflowStoreActions` | `batchRemoveNodesAndEdges({ nodeIds, edges })` (React Flow IDs) |
| Mark workflow as saved     | `useWorkflowStoreActions` | `const { markClean } = useWorkflowStoreActions()`               |
| Create a new task          | `createScriptActivity`    | `createScriptActivity(id, name, lang, code)`                    |
| Access state outside React | `useWorkflowStore`        | `useWorkflowStore.getState().currentWorkflow`                   |

---

## Summary

| Pattern         | When to Use                 | Import                        |
| --------------- | --------------------------- | ----------------------------- |
| Custom Hooks    | Reading state in components | `useWorkflowVersion`, etc.    |
| Action Accessor | Dispatching actions only    | `useWorkflowStoreActions`     |
| Typed Selectors | Complex/custom selections   | `selectActivities`, etc.      |
| Direct Access   | Outside React, callbacks    | `useWorkflowStore.getState()` |

The architecture prioritizes:

1. **Type safety** - Full TypeScript support
2. **Performance** - Selective subscriptions by default
3. **Simplicity** - Clean, intuitive API
4. **Atomicity** - Batch operations for coupled state
5. **Testability** - Easy to mock and test

---

---

## Other Zustand Stores

### Execution Store (`useExecutionStore`)

The execution visualization uses a dedicated Zustand store:

```text
packages/syntara-ui/src/routes/workflows/stores/useExecutionStore.ts
```

| Purpose               | Description                                                     |
| --------------------- | --------------------------------------------------------------- |
| Track execution state | Current execution ID, visualization data, completion status     |
| Activity-level states | Per-activity execution status and error tracking                |
| WebSocket integration | Connection state, staleness detection, last event ID for replay |
| Incremental updates   | Apply patches from WebSocket messages to update activity states |

**Key state:**

| Field            | Type                         | Description                                              |
| ---------------- | ---------------------------- | -------------------------------------------------------- |
| `executionId`    | `string \| null`             | Currently tracked execution                              |
| `visualization`  | `object \| null`             | Full visualization snapshot from backend                 |
| `activityStates` | `Map<string, ActivityState>` | Per-activity execution status, timing, and error details |
| `activityErrors` | `Map<string, string>`        | Per-activity error messages                              |
| `isConnected`    | `boolean`                    | WebSocket connection state                               |
| `isComplete`     | `boolean`                    | Whether execution has finished                           |
| `lastEventId`    | `string \| null`             | Last processed event (for replay on reconnect)           |

**Key actions:** `setExecution`, `applyPatch`, `setComplete`, `setConnectionState`, `setActivityExecutions`, `reset`

> See [`docs/execution-visualizer-protocol.md`](./execution-visualizer-protocol.md) for the full execution WebSocket protocol.

### WebSocket Store (`useWebSocketStore`)

The WebSocket infrastructure uses a dedicated Zustand store in `lib/websocket/`:

```text
packages/syntara-ui/src/lib/websocket/store.ts
```

| Purpose                    | Description                                                 |
| -------------------------- | ----------------------------------------------------------- |
| Track connection states    | Per-channel connection status (connecting, connected, etc.) |
| Manage WebSocket instances | Native WebSocket creation, reconnection, cleanup            |
| Message routing            | Route messages to subscribers via callback pattern          |
| Reconnection logic         | Exponential backoff with configurable attempts              |

**Primary hooks (from `lib/websocket/hooks.ts`):**

| Hook                             | Purpose                                        |
| -------------------------------- | ---------------------------------------------- |
| `useWebSocket(channel, options)` | Connect to channel, get send/state/controls    |
| `useWebSocketState`              | Get connection state only (minimal re-renders) |

**Store selectors (from `lib/websocket/store.ts`):**

| Selector                    | Returns             | Use case                      |
| --------------------------- | ------------------- | ----------------------------- |
| `selectConnectionState(id)` | ConnectionState     | Get channel connection state  |
| `selectIsConnected(id)`     | boolean             | Check if channel is connected |
| `selectError(id)`           | string \| undefined | Get last error for channel    |

**Usage pattern:**

```tsx
import { useWebSocket, WebSocketChannel } from '../../lib/websocket'

function ChatComponent() {
  const { connectionState, isConnected, sendRaw } = useWebSocket(WebSocketChannel.Chat, {
    onMessage: (msg) => console.log('Received:', msg),
  })

  return (
    <div>
      <Badge color={isConnected ? 'green' : 'red'}>{connectionState}</Badge>
      <button onClick={() => sendRaw({ text: 'Hello' })}>Send</button>
    </div>
  )
}
```

> See [`docs/websocket-architecture.md`](./websocket-architecture.md) for comprehensive WebSocket documentation.

### Auth Store (`useAuthStore`)

```text
packages/syntara-ui/src/stores/useAuthStore.ts
```

| Purpose                     | Description                                                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Token management            | Access token storage, refresh, and expiry tracking                                                                                               |
| Session lifecycle           | Login, logout, and session persistence                                                                                                           |
| Auth middleware integration | Provides tokens to API client `authMiddleware`                                                                                                   |
| Query cache invalidation    | Calls `queryClient.clear()` on `logout()`, `clearAuth()`, and `refresh()` failure — prevents stale permission cache leaking across user sessions |

### Project Store (`useProjectStore`)

```text
packages/syntara-ui/src/stores/useProjectStore.ts
```

| Purpose         | Description                                |
| --------------- | ------------------------------------------ |
| Active project  | Tracks which project is currently selected |
| Project scoping | Scopes API queries to the active project   |

---

## Further Reading

- [Zustand docs](https://docs.pmnd.rs/zustand/getting-started/introduction)
- [Preventing re-renders with selectors](https://docs.pmnd.rs/zustand/guides/prevent-rerenders-with-use-shallow)
- [TypeScript guide](https://docs.pmnd.rs/zustand/guides/typescript)
