import type { Activity, WorkflowAPI } from '@syntara/contracts'

import { API_EXECUTOR_TYPES, type ApiExecutorType } from '../constants/executorTypes'
import type { EdgeConnection } from '../routes/builder/types/edge'

// Re-export v2 node types for backward compatibility
export type { Activity, TaskActivity } from '@syntara/contracts'

// Type aliases from API contracts (v2)
export type WorkflowDefinitionBase = WorkflowAPI.components['schemas']['WorkflowDefinition']

// V2 trigger — uses the practical Activity interface (not the generated type
// which has config: Record<string, never>)
export type Trigger = Activity

/**
 * Extended workflow definition used by the store.
 *
 * The v2 API schema uses `nodes` for the activities array, but the store
 * keeps the `workflow.activities` shape internally for backward-compatible
 * access across the codebase.  The `triggers` field is widened to accept
 * v2 trigger nodes.
 */
export type WorkflowDefinition = Omit<WorkflowDefinitionBase, 'triggers' | 'nodes' | 'edges' | '$defs'> & {
  triggers?: Trigger[]
  /** Internal store representation — maps to v2 `nodes` on save */
  workflow: {
    activities: Activity[]
  }
  /** Whether this is a built-in workflow */
  is_builtin?: boolean
  /** Optional metadata from the API (labels, etc.) */
  metadata?: Record<string, unknown>
}

/**
 * Runtime metadata added by the UI to activities (not part of the API contract).
 * Used for generic placeholder nodes and layout hints.
 *
 * SECURITY: This interface is intentionally restrictive. Only explicitly
 * listed properties are allowed. Do NOT add a catch-all index signature
 * like `[key: string]: unknown` as it would allow arbitrary metadata
 * injection that could bypass type safety in security-sensitive code
 * paths (e.g., executor type detection in detectTaskNodeType).
 */
export type ActivityMetadata = {
  __isGeneric?: boolean
  __customMessage?: string
  __reverseHandles?: boolean
  /**
   * Executor type override for display purposes only.
   * SECURITY: Type-restricted to allowlist for compile-time safety.
   * Runtime validation also exists in detectTaskNodeType().
   */
  __executorType?: ApiExecutorType
  /**
   * Set during test executions to indicate this node's input data was
   * pre-resolved (mocked) instead of computed from upstream activities.
   */
  __mockDataPinned?: boolean
}

/**
 * Activity extended with UI-only runtime metadata.
 * Use this type when creating activities with metadata in the UI.
 * Avoids unsafe `as Activity` casts that bypass type checking.
 */
export type ActivityWithMetadata = Activity & {
  metadata?: ActivityMetadata
}

/**
 * Sanitizes a raw metadata object by copying only allowlisted properties.
 * SECURITY: Prevents metadata injection from untrusted API responses.
 */
function sanitizeMetadata(raw: Record<string, unknown>): ActivityMetadata {
  const sanitized: ActivityMetadata = {}

  if ('__isGeneric' in raw) {
    sanitized.__isGeneric = Boolean(raw.__isGeneric)
  }
  if ('__customMessage' in raw && typeof raw.__customMessage === 'string') {
    sanitized.__customMessage = raw.__customMessage
  }
  if ('__reverseHandles' in raw) {
    sanitized.__reverseHandles = Boolean(raw.__reverseHandles)
  }
  if (
    '__executorType' in raw &&
    typeof raw.__executorType === 'string' &&
    API_EXECUTOR_TYPES.has(raw.__executorType as ApiExecutorType)
  ) {
    sanitized.__executorType = raw.__executorType as ApiExecutorType
  }
  if ('__mockDataPinned' in raw && raw.__mockDataPinned === true) {
    sanitized.__mockDataPinned = true
  }

  return sanitized
}

/**
 * Safely extract and sanitize the `metadata` bag from untrusted activity data.
 * SECURITY: Only allowlisted properties are copied to prevent metadata injection.
 * The API contract `Activity` type does not include `metadata`, so direct
 * property access would be flagged as unsafe by typescript-eslint.
 */
export function getActivityMetadata(activity: unknown): ActivityMetadata | undefined {
  if (!activity || typeof activity !== 'object') {
    return undefined
  }

  if (!Object.hasOwn(activity, 'metadata')) {
    return undefined
  }

  const raw = (activity as { metadata?: unknown }).metadata
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined
  }

  return sanitizeMetadata(raw as Record<string, unknown>)
}

export type WorkflowStore = {
  currentWorkflow: WorkflowDefinition | null
  /**
   * Project ID that the current workflow belongs to.
   * Stored separately from workflow definition for permission checks.
   */
  projectId: string | null
  /**
   * UI-only counter to force React Flow recomputation.
   * Incremented when setWorkflow/loadWorkflowWithEdges/batchAddActivitiesAndEdges is called.
   * NOT related to backend workflow.version or workflow.current_version fields.
   */
  workflowVersion: number
  edges: EdgeConnection[]
  /** Canvas positions keyed by node ID (activity or trigger display ID). */
  nodePositions: Record<string, { x: number; y: number }>
  /**
   * UI-only counter incremented when undo/redo restores only node positions
   * (no workflow content change).  BuilderFlow subscribes to this to apply
   * positions in-place without a full React Flow re-initialization cycle.
   * NOT partialized — temporal does not track this.
   */
  _positionUndoVersion: number
  /**
   * When true, the edge sync should resume temporal tracking after pushing edges.
   * Set by addActivity / batchAddActivitiesAndEdges
   * to group the node change + subsequent derived edge sync into one undo entry.
   * NOT partialized — temporal does not track this.
   */
  _temporalBatchPending: boolean
  /**
   * When true, the post-layout undo-history clear is skipped once, then
   * this flag resets to false.  Set by replaceWorkflowContent so that
   * import-into-existing remains undoable after re-layout.
   * NOT partialized — temporal does not track this.
   */
  _preserveHistoryOnLayout: boolean
  /**
   * Whether nodePositions represent user intent (drag, API load, import)
   * and should be serialized into the workflow definition on save/export.
   * false when positions are only auto-layout computed or were cleared.
   */
  _positionsUserModified: boolean
  isDirty: boolean // Tracks whether changes have been made since last save/load
  _undoBaselineMatchesSave: boolean // true when temporal baseline (pastStates=0) is the saved state
  _nonTemporalDirty: boolean // true when markDirty() was called for changes not tracked by undo
  validationErrorCount: number // Number of errors from last verification; persists until re-verify
  setValidationErrorCount: (count: number) => void
  setWorkflow: (workflow: WorkflowDefinition | null, projectId?: string | null) => void
  // Atomic operation to load workflow and edges together - prevents race conditions
  loadWorkflowWithEdges: (
    workflow: WorkflowDefinition,
    edges: EdgeConnection[],
    nodePositions?: Record<string, { x: number; y: number }>,
    projectId?: string | null
  ) => void
  markClean: () => void // Called after successful save
  markDirty: () => void // Called when metadata changes
  /**
   * Update the current workflow without incrementing workflowVersion.
   *
   * Use this for incremental updates to an already-loaded workflow (e.g. applying
   * externally computed changes) where consumers should react to the changed
   * workflow content, but the workflow "identity" has not changed.
   */
  updateWorkflow: (updater: (workflow: WorkflowDefinition) => WorkflowDefinition) => void
  setEdges: (edges: EdgeConnection[]) => void
  addTrigger: (trigger: Trigger) => void
  removeTrigger: (index: number) => void
  updateTrigger: (index: number, trigger: Trigger) => void
  addActivity: (activity: Activity) => void
  removeActivity: (activityId: string) => void
  updateActivity: (activityId: string, updates: Partial<Activity>) => void
  /**
   * Fully replace an activity in the list, discarding all type-specific fields
   * from the old activity. Unlike `updateActivity`, this does NOT merge — the
   * replacement activity is inserted as-is (with `id` overridden to the target ID).
   */
  replaceActivity: (activityId: string, newActivity: Activity) => void
  /**
   * Deep-clone an activity, assign it a new ID, derive a unique "Copy of…"
   * name, and append it to the flat activities list.
   *
   * @returns The new activity's ID, or null when the source activity is not found.
   */
  duplicateActivity: (activityId: string) => string | null
  updateSwitchActivity: (nodeId: string, updatedActivity: Activity, portMapping: Map<string, string>) => void
  moveActivityBefore: (activityId: string, beforeActivityId: string) => void
  moveActivityAfter: (activityId: string, afterActivityId: string) => void
  syncConvergeNodeBranches: () => void
  reorderActivitiesFromEdges: () => void
  // Atomic batch update to prevent race conditions
  batchRemoveNodesAndEdges: (params: { nodeIds: string[]; edges: EdgeConnection[]; triggerIndices?: number[] }) => void
  batchAddActivitiesAndEdges: (params: { activities: Activity[]; edges: EdgeConnection[] }) => void
  /**
   * Replace workflow content in-place, preserving undo history.
   * Used by import-into-existing so the user can undo the import.
   * Unlike loadWorkflowWithEdges, this does NOT clear temporal history.
   */
  replaceWorkflowContent: (
    workflow: WorkflowDefinition,
    edges: EdgeConnection[],
    nodePositions?: Record<string, { x: number; y: number }>
  ) => void
  /** Batch-update canvas positions (merges with existing). */
  updateNodePositions: (
    positions: Record<string, { x: number; y: number }>,
    options?: { markDirty?: boolean; skipTracking?: boolean }
  ) => void
  /** Clear all stored node positions so auto-layout runs on next load. */
  clearNodePositions: () => void
}
