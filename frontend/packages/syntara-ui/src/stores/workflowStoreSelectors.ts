import { useStore } from 'zustand'

import { edgesEqual, useWorkflowStore, workflowEqual } from './useWorkflowStore'
import type { WorkflowStore } from './workflowStoreTypes'

// ============================================================================
// Typed Selectors - Use these for optimized component subscriptions
// ============================================================================
// These selectors help prevent unnecessary re-renders by subscribing to
// specific pieces of state rather than the entire store.
//
// Best Practice: Use these selectors instead of inline selectors for:
// 1. Better type inference
// 2. Reusability across components
// 3. Consistent state access patterns
// ============================================================================

/**
 * Selector for the current workflow.
 * Use when you need the entire workflow object.
 */
export const selectCurrentWorkflow = (state: WorkflowStore) => state.currentWorkflow

/**
 * Selector for workflow version counter (UI-only).
 * Use to detect when a completely new workflow has been loaded or batch operations complete.
 * This is a UI-only counter - NOT related to backend workflow.version or workflow.current_version.
 * Incremented by: setWorkflow, loadWorkflowWithEdges, and content undo/redo (wrappedUndo / wrappedRedo).
 * Does NOT change when individual activities/triggers/edges are modified.
 */
export const selectWorkflowVersion = (state: WorkflowStore) => state.workflowVersion

/**
 * Selector for edges array.
 * Use when working with workflow connections.
 */
export const selectEdges = (state: WorkflowStore) => state.edges

/**
 * Selector for activities array.
 * Use when you need to map over or filter activities.
 */
export const selectActivities = (state: WorkflowStore) => state.currentWorkflow?.workflow.activities

/**
 * Selector for triggers array.
 * Use when you need to map over or filter triggers.
 */
export const selectTriggers = (state: WorkflowStore) => state.currentWorkflow?.triggers

/**
 * Selector for activities count.
 * Use when you only need to know the number of activities (e.g., for conditional rendering).
 */
export const selectActivitiesCount = (state: WorkflowStore) => state.currentWorkflow?.workflow.activities.length ?? 0

/**
 * Selector for triggers count.
 * Use when you only need to know the number of triggers (e.g., for conditional rendering).
 */
export const selectTriggersCount = (state: WorkflowStore) => state.currentWorkflow?.triggers?.length ?? 0

/**
 * Selector for isDirty flag.
 * Use to check if there are unsaved changes.
 */
export const selectIsDirty = (state: WorkflowStore) => state.isDirty

/**
 * Selector for workflow name.
 * Use when you only need the workflow name (e.g., for display in header).
 */
export const selectWorkflowName = (state: WorkflowStore) =>
  state.currentWorkflow?.name ?? state.currentWorkflow?.metadata?.name

/**
 * Selector to check if a workflow is loaded.
 * Use for conditional rendering based on workflow presence.
 */
export const selectHasWorkflow = (state: WorkflowStore) => state.currentWorkflow !== null

// ============================================================================
// Action Accessors - Use these to access actions without subscribing to state
// ============================================================================
// Zustand best practice: When you only need to call actions (not read state),
// use getState() to avoid unnecessary re-renders.
//
// Example:
//   const { addActivity, removeActivity } = useWorkflowStoreActions()
//   // Component won't re-render when workflow changes
// ============================================================================

/**
 * Get all store actions without subscribing to state changes.
 * Use this when you only need to dispatch actions from event handlers.
 *
 * @example
 * const { addActivity, removeActivity } = useWorkflowStoreActions()
 * const handleAdd = () => addActivity(newActivity)
 */
export const useWorkflowStoreActions = () => {
  const state = useWorkflowStore.getState()
  return {
    setWorkflow: state.setWorkflow,
    loadWorkflowWithEdges: state.loadWorkflowWithEdges,
    updateWorkflow: state.updateWorkflow,
    setEdges: state.setEdges,
    markClean: state.markClean,
    markDirty: state.markDirty,
    addTrigger: state.addTrigger,
    removeTrigger: state.removeTrigger,
    updateTrigger: state.updateTrigger,
    addActivity: state.addActivity,
    removeActivity: state.removeActivity,
    updateActivity: state.updateActivity,
    replaceActivity: state.replaceActivity,
    duplicateActivity: state.duplicateActivity,
    updateSwitchActivity: state.updateSwitchActivity,
    moveActivityBefore: state.moveActivityBefore,
    moveActivityAfter: state.moveActivityAfter,
    reorderActivitiesFromEdges: state.reorderActivitiesFromEdges,
    batchRemoveNodesAndEdges: state.batchRemoveNodesAndEdges,
    batchAddActivitiesAndEdges: state.batchAddActivitiesAndEdges,
    updateNodePositions: state.updateNodePositions,
    clearNodePositions: state.clearNodePositions,
  }
}

/**
 * Type for workflow store actions (useful for typing event handlers).
 */
export type WorkflowStoreActions = ReturnType<typeof useWorkflowStoreActions>

// ============================================================================
// Custom Hooks - Recommended way to access store state
// ============================================================================
// These hooks provide controlled access to specific state slices.
// Prefer using these over direct store access for better encapsulation.
// ============================================================================

/** Hook to get workflow version counter (UI-only, NOT backend workflow.version) */
export const useWorkflowVersion = () => useWorkflowStore(selectWorkflowVersion)

/** Hook to get the current workflow */
export const useCurrentWorkflow = () => useWorkflowStore(selectCurrentWorkflow)

/** Hook to get edges */
export const useEdges = () => useWorkflowStore(selectEdges)

/** Hook to get activities */
export const useActivities = () => useWorkflowStore(selectActivities)

/** Hook to get triggers */
export const useTriggers = () => useWorkflowStore(selectTriggers)

/** Hook to get activities count */
export const useActivitiesCount = () => useWorkflowStore(selectActivitiesCount)

/** Hook to get triggers count */
export const useTriggersCount = () => useWorkflowStore(selectTriggersCount)

/** Hook to get workflow name */
export const useWorkflowName = () => useWorkflowStore(selectWorkflowName)

/** Hook to check if workflow is loaded */
export const useHasWorkflow = () => useWorkflowStore(selectHasWorkflow)

/**
 * Selector for position-undo version counter (UI-only).
 * Incremented when undo/redo restores only canvas positions (no content change).
 */
export const selectPositionUndoVersion = (state: WorkflowStore) => state._positionUndoVersion

// ============================================================================
// Undo/Redo (zundo temporal store)
// ============================================================================

/**
 * Determines whether the undo/redo changed workflow content (nodes, edges)
 * or only canvas positions.  Content changes need a full React Flow
 * re-initialization (`workflowVersion` bump), while position-only changes
 * can be applied in-place to preserve button edges and avoid flicker.
 */
function isContentChange(
  before: { currentWorkflow: WorkflowStore['currentWorkflow']; edges: WorkflowStore['edges'] },
  after: { currentWorkflow: WorkflowStore['currentWorkflow']; edges: WorkflowStore['edges'] }
): boolean {
  return !workflowEqual(before.currentWorkflow, after.currentWorkflow) || !edgesEqual(before.edges, after.edges)
}

/**
 * Pauses temporal tracking around undo/redo so that the inevitable
 * `useEdgeSynchronization` re-sync (local → store) that follows the React
 * render cycle does not push a duplicate snapshot onto the undo stack.
 * Tracking resumes on the next tick, after React has flushed.
 *
 * For content changes (added/removed nodes/edges), bumps `workflowVersion`
 * to force a clean React Flow re-initialization.
 * For position-only changes (dragged nodes), bumps `_positionUndoVersion`
 * so BuilderFlow can apply positions in-place without full re-init.
 */
export function wrappedUndo(steps?: number) {
  const temporal = useWorkflowStore.temporal.getState()
  if (temporal.pastStates.length === 0) return
  temporal.pause()
  const before = useWorkflowStore.getState()
  temporal.undo(steps)
  const after = useWorkflowStore.getState()
  if (isContentChange(before, after)) {
    // Preserve redo stack: the workflowVersion bump triggers re-initialization
    // which calls clearUndoHistory → temporal.clear(). Setting this flag makes
    // clearUndoHistory skip the clear so futureStates (redo) survive.
    useWorkflowStore.setState((s) => ({
      workflowVersion: s.workflowVersion + 1,
      _preserveHistoryOnLayout: true,
    }))
  } else {
    useWorkflowStore.setState((s) => ({ _positionUndoVersion: s._positionUndoVersion + 1 }))
  }
  const state = useWorkflowStore.getState()
  const atCleanBaseline = temporal.pastStates.length === 0 && state._undoBaselineMatchesSave && !state._nonTemporalDirty
  useWorkflowStore.setState({ isDirty: !atCleanBaseline })
  setTimeout(() => temporal.resume(), 0)
}

export function wrappedRedo(steps?: number) {
  const temporal = useWorkflowStore.temporal.getState()
  if (temporal.futureStates.length === 0) return
  temporal.pause()
  const before = useWorkflowStore.getState()
  temporal.redo(steps)
  const after = useWorkflowStore.getState()
  if (isContentChange(before, after)) {
    useWorkflowStore.setState((s) => ({
      workflowVersion: s.workflowVersion + 1,
      _preserveHistoryOnLayout: true,
    }))
  } else {
    useWorkflowStore.setState((s) => ({ _positionUndoVersion: s._positionUndoVersion + 1 }))
  }
  useWorkflowStore.setState({ isDirty: true })
  setTimeout(() => temporal.resume(), 0)
}

/**
 * Hook to access undo/redo actions and state from the temporal middleware.
 *
 * Returns `{ undo, redo, canUndo, canRedo, clear }`.
 */
export function useWorkflowHistory() {
  const temporalStore = useWorkflowStore.temporal
  const canUndo = useStore(temporalStore, (s) => s.pastStates.length > 0)
  const canRedo = useStore(temporalStore, (s) => s.futureStates.length > 0)
  const clear = temporalStore.getState().clear

  return { undo: wrappedUndo, redo: wrappedRedo, canUndo, canRedo, clear }
}
