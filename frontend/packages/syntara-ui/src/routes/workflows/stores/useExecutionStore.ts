/**
 * Execution Store
 *
 * Zustand store for managing execution visualization state:
 * - Execution visualization with WebSocket streaming
 * - Activity states and errors (unified data model)
 * - WebSocket connection status
 * - Event replay for reconnection
 *
 * Used by the ExecutionDetail page (/executions/{id}) to display execution
 * details with real-time updates via WebSocket or REST API fallback.
 */

import type { ExecutionsAPI } from '@syntara/contracts'
import { create } from 'zustand'

import type {
  Execution,
  ExecutionStatus,
  ExecutionVisualization,
  JsonPatchOperation,
  ActivityState,
  ActivityStatus,
} from '../execution/types'
import { applyJsonPatch, buildActivityStateMap, extractActivityMaps } from '../execution/utils/activityState'

// ============================================================================
// Type Imports
// ============================================================================

type ActivityData = ExecutionsAPI.components['schemas']['ActivityData']
type ActivityExecution = ExecutionsAPI.components['schemas']['ActivityExecution']

/** Activity input from REST API: Execution.activities (ActivityData) or list endpoint (ActivityExecution) */
type ActivityInput = ActivityData | ActivityExecution

/**
 * Typed shape for execution_metadata from the REST API.
 * Local definition until the backend OpenAPI spec includes this field.
 */
export type ExecutionMetadata = {
  mode?: string
  pre_resolved_nodes?: Record<string, { output: Record<string, unknown> }>
}

const STATUS_ORDER: Record<string, number> = {
  pending: 0,
  running: 1,
  retrying: 1,
  waiting: 2,
  completed: 3,
  failed: 3,
  cancelled: 3,
  skipped: 3,
}

/**
 * Merge incoming activity states with existing, preserving the most advanced
 * status per-activity. This prevents stale REST/snapshot data from regressing
 * state that WebSocket patches have already advanced.
 *
 * Limitation: full retry cycles (completed→pending) are not handled here.
 * A proper solution requires sequence numbers or generation IDs from the backend.
 */
function mergeActivityStates(
  existing: Map<string, ActivityState>,
  incoming: Map<string, ActivityState>
): Map<string, ActivityState> {
  if (existing.size === 0) return incoming
  if (incoming.size === 0) return existing

  const merged = new Map(existing)
  for (const [id, incomingState] of incoming) {
    const existingState = merged.get(id)
    if (!existingState) {
      merged.set(id, incomingState)
    } else {
      const existingOrder = STATUS_ORDER[existingState.status] ?? 0
      const incomingOrder = STATUS_ORDER[incomingState.status] ?? 0
      if (incomingOrder > existingOrder) {
        merged.set(id, incomingState)
      } else if (incomingOrder === existingOrder) {
        // Preserve non-null timestamps/errors from either side so a same-rank
        // REST re-fetch cannot wipe fields already set by a WebSocket patch.
        merged.set(id, {
          ...incomingState,
          startedAt: existingState.startedAt ?? incomingState.startedAt,
          completedAt: existingState.completedAt ?? incomingState.completedAt,
          errorDetails: existingState.errorDetails ?? incomingState.errorDetails,
          iteration: incomingState.iteration ?? existingState.iteration,
        })
      }
    }
  }
  return merged
}

// ============================================================================
// Store State
// ============================================================================

type ExecutionStoreState = {
  // === Execution Visualization (WebSocket streaming) ===
  /** Current execution being visualized/streamed */
  executionId: string | null
  /** Full execution visualization data */
  visualization: ExecutionVisualization | null
  /** Activity states keyed by activity_id (UNIFIED - stores full ActivityState objects) */
  activityStates: Map<string, ActivityState>
  /** Activity errors keyed by activity_id (for quick error lookups) */
  activityErrors: Map<string, string>
  /** Execution metadata (includes mode, pre_resolved_nodes for test runs, etc.) */
  executionMetadata: ExecutionMetadata | null

  // === WebSocket State ===
  /** WebSocket connection state */
  isConnected: boolean
  /** Whether connection is stale (disconnected but reconnecting) */
  isStale: boolean
  /** Whether execution is complete (final_snapshot received) */
  isComplete: boolean
  /** Last event ID received (for replay on reconnection) */
  lastEventId: string | null

  // === Error State ===
  /** Error state */
  error: Error | null
}

// ============================================================================
// Store Actions
// ============================================================================

type ExecutionStoreActions = {
  // === Execution Visualization Actions ===
  /**
   * Set execution data from REST API or WebSocket snapshot
   * Initializes or updates the complete execution state
   */
  setExecution: (execution: Execution) => void

  /**
   * Apply JSON Patch operations from WebSocket activity_patch message
   * Updates activity states incrementally
   */
  applyPatch: (ops: JsonPatchOperation[], eventId: string) => void

  /**
   * Apply JSON Patch operations from WebSocket execution_patch message
   * Updates execution-level fields (e.g. status) incrementally
   */
  applyExecutionPatch: (ops: JsonPatchOperation[], eventId: string) => void

  /**
   * Mark execution as complete (received final_snapshot)
   * Stops WebSocket streaming
   */
  setComplete: (complete: boolean) => void

  /**
   * Update WebSocket connection state
   */
  setConnectionState: (connected: boolean, stale: boolean) => void

  /**
   * Update last received event ID for replay support
   */
  setLastEventId: (eventId: string) => void

  /**
   * Set error state
   */
  setError: (error: Error | null) => void

  // === ExecutionDetail Page Actions ===
  /**
   * Set activity executions for ExecutionDetail page (auto-converts to ActivityState)
   * Accepts ActivityData[] (from Execution.activities) or ActivityExecution[] (from list endpoint)
   * Used by ExecutionDetailsPanel when loading execution data via REST API
   */
  setActivityExecutions: (activities: ActivityInput[]) => void

  /**
   * Inject pending activity states from workflow definition node IDs.
   * Used by useSyncActivityStore to seed the store before real activity data arrives.
   */
  injectPendingStates: (nodeIds: string[]) => void

  /**
   * Inject SKIPPED states for pre-resolved nodes that lack backend activity records.
   * Handles the race condition where the backend hasn't synced ActivityExecution records yet.
   */
  injectPreResolvedStates: (missingNodeIds: string[]) => void

  /**
   * Set execution metadata (mode, pre_resolved_nodes for test runs, etc.)
   */
  setExecutionMetadata: (metadata: ExecutionMetadata | null) => void

  // === Reset ===
  /**
   * Reset entire store to initial state
   * Used when switching between executions or unmounting
   */
  reset: () => void
}

// ============================================================================
// Complete Store Type
// ============================================================================

type ExecutionStore = ExecutionStoreState & ExecutionStoreActions

// ============================================================================
// Adapter Functions
// ============================================================================

/**
 * Runtime validator for activity status values.
 * Validates against the explicit ActivityStatus union and returns a safe status.
 * Falls back to 'pending' for invalid/unknown values.
 */
function normalizeActivityStatus(status: unknown): ActivityStatus {
  const validStatuses: ActivityStatus[] = [
    'pending',
    'running',
    'waiting',
    'completed',
    'failed',
    'retrying',
    'skipped',
    'cancelled',
  ]
  if (typeof status === 'string' && validStatuses.includes(status as ActivityStatus)) {
    return status as ActivityStatus
  }
  return 'pending'
}

/**
 * Get activity ID from ActivityData or ActivityExecution
 * ActivityData uses activity_id; ActivityExecution uses activity_name or id
 */
function getActivityId(activity: ActivityInput): string | undefined {
  if ('activity_id' in activity) {
    return activity.activity_id
  }
  return activity.activity_name ?? activity.id
}

/**
 * Convert API ActivityData or ActivityExecution to internal ActivityState
 * Used by ExecutionDetailsPanel when loading execution data via REST API
 */
function activityInputToState(activity: ActivityInput): ActivityState {
  const activityId = getActivityId(activity)
  if (!activityId) {
    throw new Error('Activity must have activity_id (ActivityData) or activity_name/id (ActivityExecution)')
  }
  return {
    activityId,
    status: normalizeActivityStatus(activity.status),
    errorDetails: activity.error_details,
    outputData: activity.output_data,
    startedAt: activity.started_at,
    completedAt: activity.completed_at,
    iteration: activity.iteration ?? undefined,
  }
}

/**
 * Convert array of ActivityData or ActivityExecution to maps for fast lookup
 * Used by ExecutionDetailsPanel's setActivityExecutions action
 */
function buildActivityMapsFromInput(activities: ActivityInput[]): [Map<string, ActivityState>, Map<string, string>] {
  const activityStates = new Map<string, ActivityState>()
  const activityErrors = new Map<string, string>()

  activities.forEach((activity) => {
    const activityKey = getActivityId(activity)
    if (activityKey) {
      const activityState = activityInputToState(activity)
      activityStates.set(activityKey, activityState)

      if (activity.error_details) {
        activityErrors.set(activityKey, activity.error_details)
      }
    }
  })

  return [activityStates, activityErrors]
}

/**
 * Create a pending ActivityState for a node that has no backend activity record yet.
 * Used by useSyncActivityStore to seed the store from the workflow definition
 * before real activity data arrives from the backend or WebSocket.
 */
export function createPendingActivityState(nodeId: string): ActivityState {
  return {
    activityId: nodeId,
    status: 'pending',
    startedAt: null,
    completedAt: null,
    errorDetails: null,
  }
}

// ============================================================================
// Initial State
// ============================================================================

const initialState: ExecutionStoreState = {
  // Execution Visualization
  executionId: null,
  visualization: null,
  activityStates: new Map(),
  activityErrors: new Map(),
  executionMetadata: null,

  // WebSocket State
  isConnected: false,
  isStale: false,
  isComplete: false,
  lastEventId: null,

  // Error State
  error: null,
}

// ============================================================================
// Store Implementation
// ============================================================================

/**
 * Execution Store Implementation
 *
 * Supports execution visualization for the ExecutionDetail page (/executions/{id}).
 *
 * **Data Population:**
 * - Primary: setExecution() via WebSocket initial_snapshot for real-time streaming
 * - Fallback: setActivityExecutions() via REST API (ExecutionDetailsPanel)
 *
 * **Data Flow:**
 * 1. REST API: GET /executions/{id}?include=workflow_definition,activities
 *    → Initial load via setActivityExecutions() (ExecutionDetailsPanel)
 * 2. WebSocket (optional): Connect to streaming endpoint for running executions
 *    → initial_snapshot: Full state via setExecution()
 *    → activity_patch: Incremental updates via applyPatch()
 *    → final_snapshot: Execution complete, refetch REST data
 * 3. Canvas: BuilderFlow/ExecutionViewContent subscribe to activityStates
 *    → Node badges update automatically when state changes
 *
 * **Note:** If both setExecution() and setActivityExecutions() are called,
 * activity states are merged via mergeActivityStates — the most advanced
 * status rank wins, and equal-rank merges preserve non-null timestamps/errors.
 */
export const useExecutionStore = create<ExecutionStore>((set, get) => ({
  ...initialState,

  // === Execution Visualization Actions ===

  setExecution: (execution: Execution) => {
    // Build activity state map from execution data
    const activities = (execution.activities ?? []).map((activity) => ({
      activity_id: activity.activity_id,
      status: normalizeActivityStatus(activity.status),
      error_details: activity.error_details,
      output_data: activity.output_data,
      started_at: activity.started_at,
      completed_at: activity.completed_at,
      iteration: activity.iteration,
    }))
    const activityStateMap = buildActivityStateMap(activities)

    const existing = get().activityStates
    const effectiveActivities = mergeActivityStates(existing, activityStateMap)

    // Extract error map for fast lookups (activityStates will be the full map)
    const [, activityErrors] = extractActivityMaps(effectiveActivities)

    // Build visualization object
    const visualization: ExecutionVisualization = {
      executionId: execution.id,
      workflowId: execution.workflow_id ?? '',
      status: execution.status ?? 'pending',
      approval_pending: execution.approval_pending ?? false,
      workflowDefinition: execution.workflow_definition,
      activities: effectiveActivities,
      createdAt: execution.created_at,
      startedAt: execution.created_at,
      completedAt: execution.completed_at,
    }

    // Extract execution metadata for test runs (mode, pre_resolved_nodes, etc.)
    const executionMetadata = (execution as { execution_metadata?: ExecutionMetadata }).execution_metadata ?? null

    set({
      executionId: execution.id,
      visualization,
      activityStates: effectiveActivities,
      activityErrors,
      executionMetadata,
      error: null,
    })
  },

  applyPatch: (ops: JsonPatchOperation[], eventId: string) => {
    const { visualization, activityStates } = get()

    // Use visualization.activities when available, fall back to activityStates
    // (REST-loaded via setActivityExecutions before initial_snapshot arrives)
    const baseActivities = visualization?.activities ?? activityStates

    const activitiesCopy = new Map(baseActivities)

    try {
      const activityArray = Array.from(activitiesCopy.values())
      applyJsonPatch(activitiesCopy, ops, activityArray)

      const [, activityErrors] = extractActivityMaps(activitiesCopy)

      if (visualization) {
        set({
          visualization: { ...visualization, activities: activitiesCopy },
          activityStates: activitiesCopy,
          activityErrors,
          lastEventId: eventId,
          error: null,
        })
      } else {
        set({
          activityStates: activitiesCopy,
          activityErrors,
          lastEventId: eventId,
          error: null,
        })
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error : new Error(String(error)),
      })
    }
  },

  applyExecutionPatch: (ops: JsonPatchOperation[], eventId: string) => {
    const { visualization } = get()
    if (!visualization) return

    let updated = visualization
    for (const op of ops) {
      if (op.op === 'replace' && op.path === '/status' && typeof op.value === 'string') {
        updated = { ...updated, status: op.value as ExecutionStatus }
      } else if (op.op === 'replace' && op.path === '/approval_pending' && typeof op.value === 'boolean') {
        updated = { ...updated, approval_pending: op.value }
      }
    }

    set({ visualization: updated, lastEventId: eventId })
  },

  setComplete: (complete: boolean) => {
    set({ isComplete: complete })
  },

  setConnectionState: (connected: boolean, stale: boolean) => {
    set({
      isConnected: connected,
      isStale: stale,
    })
  },

  setLastEventId: (eventId: string) => {
    set({ lastEventId: eventId })
  },

  setError: (error: Error | null) => {
    set({ error })
  },

  // === ExecutionDetail Page Actions ===

  setActivityExecutions: (activities: ActivityInput[]) => {
    if (activities.length === 0) {
      set({ activityStates: new Map(), activityErrors: new Map() })
      return
    }

    // Convert ActivityData[] or ActivityExecution[] to activity state maps
    const [incoming] = buildActivityMapsFromInput(activities)

    const activityStates = mergeActivityStates(get().activityStates, incoming)
    const [, activityErrors] = extractActivityMaps(activityStates)

    set({
      activityStates,
      activityErrors,
    })
  },

  injectPendingStates: (nodeIds: string[]) => {
    if (nodeIds.length === 0) return
    const incoming = new Map<string, ActivityState>()
    for (const id of nodeIds) {
      incoming.set(id, createPendingActivityState(id))
    }
    const activityStates = mergeActivityStates(get().activityStates, incoming)
    set({ activityStates })
  },

  injectPreResolvedStates: (missingNodeIds: string[]) => {
    if (missingNodeIds.length === 0) return
    const updated = new Map(get().activityStates)
    for (const id of missingNodeIds) {
      if (!updated.has(id)) {
        updated.set(id, {
          activityId: id,
          status: 'skipped' as const,
          startedAt: null,
          completedAt: null,
          errorDetails: null,
        })
      }
    }
    set({ activityStates: updated })
  },

  setExecutionMetadata: (metadata: Record<string, unknown> | null) => {
    set({ executionMetadata: metadata })
  },

  // === Reset ===

  reset: () => {
    set({
      ...initialState,
      // Reset with new Map instances to avoid reference issues
      activityStates: new Map(),
      activityErrors: new Map(),
      executionMetadata: null,
    })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

/**
 * Select execution ID (for visualization/streaming)
 */
export const selectExecutionId = (state: ExecutionStore) => state.executionId

/**
 * Select visualization data
 */
export const selectVisualization = (state: ExecutionStore) => state.visualization

/**
 * Select activity status by ID (returns just the ActivityStatus)
 */
export const selectActivityStatus = (activityId: string) => (state: ExecutionStore) =>
  state.activityStates.get(activityId)?.status

/**
 * Select activity error by ID
 */
export const selectActivityError = (activityId: string) => (state: ExecutionStore) =>
  state.activityErrors.get(activityId)

/**
 * Select connection state
 */
export const selectConnectionState = (state: ExecutionStore) => ({
  isConnected: state.isConnected,
  isStale: state.isStale,
})

/**
 * Select completion state
 */
export const selectIsComplete = (state: ExecutionStore) => state.isComplete

/**
 * Select last event ID for replay
 */
export const selectLastEventId = (state: ExecutionStore) => state.lastEventId

/**
 * Select error state
 */
export const selectError = (state: ExecutionStore) => state.error

/**
 * Select whether execution is loaded
 */
export const selectIsLoaded = (state: ExecutionStore) => state.visualization !== null

// ============================================================================
// Action Accessors - Use these to access actions without subscribing to state
// ============================================================================
// Zustand best practice: When you only need to call actions (not read state),
// use getState() to avoid unnecessary re-renders.
//
// Example:
//   const { setExecution, reset } = useExecutionStoreActions()
//   // Component won't re-render when execution changes
// ============================================================================

/**
 * Get all store actions without subscribing to state changes.
 * Use this when you only need to dispatch actions from event handlers.
 *
 * @example
 * const { setExecution, setActivityExecutions } = useExecutionStoreActions()
 * const handleLoad = () => setExecution(executionData)
 */
export const useExecutionStoreActions = () => {
  const state = useExecutionStore.getState()
  return {
    // Visualization Actions
    setExecution: state.setExecution,
    applyPatch: state.applyPatch,
    setComplete: state.setComplete,
    setConnectionState: state.setConnectionState,
    setLastEventId: state.setLastEventId,
    setError: state.setError,

    // ExecutionDetail Page Actions
    setActivityExecutions: state.setActivityExecutions,

    // Reset
    reset: state.reset,
  }
}

/**
 * Type for execution store action accessors (useful for typing event handlers).
 */
export type ExecutionStoreActionAccessors = ReturnType<typeof useExecutionStoreActions>

// ============================================================================
// Custom Hooks - Recommended way to access store state
// ============================================================================
// These hooks provide controlled access to specific state slices.
// Prefer using these over direct store access for better encapsulation.
// ============================================================================

type ExecutionRead = ExecutionsAPI.components['schemas']['ExecutionRead']

/**
 * Overlay live WebSocket status onto query data so downstream components
 * always see the most recent execution status without extra props.
 */
export function useExecutionWithLiveStatus<T extends ExecutionRead | undefined>(data: T): T {
  const liveStatus = useExecutionStore((s) => s.visualization?.status)
  const liveApprovalPending = useExecutionStore((s) => s.visualization?.approval_pending)
  if (!data) return data

  // If no WebSocket visualization, return data as-is
  if (liveStatus === undefined) return data

  // Merge WebSocket visualization data with API data
  return {
    ...data,
    status: liveStatus,
    approval_pending: liveApprovalPending ?? data.approval_pending,
  }
}
