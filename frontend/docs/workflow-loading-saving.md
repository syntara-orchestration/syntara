# Workflow Loading and Saving

This document explains how workflows are loaded from the v2 API, edited in the builder, and saved back.

**Terminology:** The UI and validation messages use **step** on the canvas. This document uses **activity** and API **`nodes[]`** where they match the backend and store. React Flow exposes **`Node` / `nodes[]`** in code — see [architecture.md](./architecture.md) for the glossary.

---

## Table of Contents

1. [Overview](#overview)
2. [V2 API Format](#v2-api-format)
3. [Loading Process](#loading-process)
4. [Editing in Builder](#editing-in-builder)
5. [Saving Process](#saving-process)
6. [Handle Types](#handle-types)
7. [Edge Validation](#edge-validation)
8. [Key Files](#key-files)
9. [Troubleshooting](#troubleshooting)

---

## Overview

With the v2 API, both the backend and builder use the **same flat format**: `{ triggers[], nodes[], edges[] }`. No nested↔flat transformation is needed.

```text
API (v2 flat) → Load (port mapping) → Builder (flat) → Edit → Save (port mapping) → API (v2 flat)
```

The only transformation between API and builder is **port name mapping** (e.g., `from_port: 'when_true'` ↔ `sourceHandle: 'true'`).

## V2 API Format

```typescript
{
  schema_version: '2.0.0',
  triggers: [
    { id: 'manual_trigger', type: 'manual_trigger', config: {} }
  ],
  nodes: [
    { id: 'condition-1', type: 'condition', config: { expression: '...' } },
    { id: 'task-1', type: 'script', config: { language: 'python', code: '...' } },
    { id: 'task-2', type: 'http_request', config: { url: '...' } }
  ],
  edges: [
    { from: 'manual_trigger', to: 'condition-1' },
    { from: 'condition-1', to: 'task-1', from_port: 'when_true' },
    { from: 'condition-1', to: 'task-2', from_port: 'when_false' }
  ]
}
```

## Loading Process

### File: `processExistingWorkflow.ts`

Reads `workflowDef.nodes` and `workflowDef.edges` directly from the API response:

1. **Maps v2 edges** to React Flow format using `v2PortToHandle()` (e.g., `when_true` → `true`)
2. **Enriches activities** with UI metadata from `getActivityMetadata()`
3. **Maps trigger IDs** from definition IDs to display IDs (`trigger-0`, `trigger-1`)
4. **Filters orphaned edges** where source/target nodes don't exist

The store is updated atomically via `loadWorkflowWithEdges()`.

### Port → Handle Mapping

| V2 API Port (`from_port`) | React Flow Handle (`sourceHandle`) |
| ------------------------- | ---------------------------------- |
| `when_true`               | `true`                             |
| `when_false`              | `false`                            |
| `iterate`                 | `loop`                             |
| `complete`                | `done`                             |
| `approved`                | `approved`                         |
| `rejected`                | `rejected`                         |
| _(none / default)_        | `source`                           |

## Editing in Builder

While editing, all activities stay in a flat array. Edges define relationships using React Flow handles.

### Condition steps

- Edges with `sourceHandle: 'true'` connect to the true branch
- Edges with `sourceHandle: 'false'` connect to the false branch

### Loop steps

- `sourceHandle: 'loop'` → enters loop body (restricted to ONE connection)
- `sourceHandle: 'done'` → exits loop after completion
- `targetHandle: 'end'` → loop-back edge (returns to loop start)

### Converge (Join) steps

- Managed by converge steps (`type: 'converge'`)
- `syncConvergeNodeBranches()` updates `converge.branches` array from incoming edges
- Branch activities remain in the main activities array

### Edge Synchronization

File: `useEdgeSynchronization.ts`

Every time edges change:

1. `syncConvergeNodeBranches()` — updates converge step branch arrays
2. `reorderActivitiesFromEdges()` — topological sort of activities

## Saving Process

### File: `workflowDefinitionBuilder.ts`

`buildWorkflowDefinition()` produces the v2 API payload:

1. **Validates all IDs** (security — rejects path traversal, injection, control chars)
2. **Maps React Flow handles** back to v2 ports via `handleToV2Port()` (e.g., `true` → `when_true`)
3. **Resolves trigger display IDs** (`trigger-0` → definition ID)
4. **Sanitizes names** (strips control characters, validates length)
5. **Builds positive ID allowlist** and validates all edge endpoints against it
6. **Returns** `{ schema_version: '2.0.0', triggers, nodes, edges }`

## Handle Types

### Condition step handles

- `sourceHandle: 'true'` — True branch connection
- `sourceHandle: 'false'` — False branch connection

### Loop step handles

- `sourceHandle: 'loop'` — Enters loop body (max ONE connection)
- `sourceHandle: 'done'` — Exits loop after completion
- `targetHandle: 'end'` — Loop-back edge

### Approval step handles

- `sourceHandle: 'approved'` — Approved branch
- `sourceHandle: 'rejected'` — Rejected branch

### Form prompt step handles

- `sourceHandle: 'submitted'` — Successful form submission branch (at least one successor required)
- `sourceHandle: 'fallback'` — Timeout / fallback routing when fallback behavior routes to the fallback port

| V2 API Port (`from_port`) | React Flow Handle (`sourceHandle`) |
| ------------------------- | ---------------------------------- |
| `submitted`               | `submitted`                        |
| `fallback`                | `fallback`                         |

### Standard Handles

- `sourceHandle: 'source'` — Default outgoing connection
- `targetHandle: 'target'` — Default incoming connection

## Edge Validation

File: `validateConnection.ts`

### Loop Handle Restriction

Only ONE edge can go out from the `loop` handle. Enforced in:

1. **`validateConnection()`** — Prevents edge creation in ReactFlow
2. **`onConnectStart()` in BuilderFlow** — Prevents drag start if handle already connected

## Key Files

| File                             | Purpose                                                     |
| -------------------------------- | ----------------------------------------------------------- |
| `processExistingWorkflow.ts`     | Load workflow from API (v2 port → handle mapping)           |
| `workflowDefinitionBuilder.ts`   | Build v2 save payload (handle → port mapping, security)     |
| `edgeHelpers.ts`                 | `v2PortToHandle()` and `handleToV2Port()` mapping functions |
| `buildNestedStructure.ts`        | Legacy wrapper (identity function in v2)                    |
| `useEdgeSynchronization.ts`      | Syncs edges with workflow store                             |
| `useBuilderWorkflowLifecycle.ts` | Orchestrates load/save lifecycle                            |
| `useWorkflowStore.ts`            | Central state management                                    |
| `validateConnection.ts`          | Edge validation rules                                       |
| `BuilderFlow.tsx`                | ReactFlow integration and edge handling                     |

## Troubleshooting

### Issue: Loop body not connected after save/load

**Cause**: Loop body edges missing or using wrong handles.
**Solution**: Verify `sourceHandle: 'loop'` for entry and `targetHandle: 'end'` for loop-back.

### Issue: Activities appear in wrong order

**Cause**: `reorderActivitiesFromEdges()` uses topological sort.
**Solution**: Check edge topology — activities follow edge order.

### Issue: Multiple edges from loop handle

**Cause**: Validation not enforced.
**Solution**: Check `validateConnection()` and `onConnectStart()`.

### Issue: Save fails with ID validation error

**Cause**: Step/edge IDs contain invalid characters.
**Solution**: IDs must be alphanumeric with hyphens, underscores, and periods only. No path traversal (`..`), control characters, or special chars.
