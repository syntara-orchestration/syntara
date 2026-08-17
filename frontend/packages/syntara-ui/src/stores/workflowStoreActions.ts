import { useWorkflowStore } from './useWorkflowStore'

/**
 * Atomically clear all workflow state and mark the store as clean.
 * Used when exiting the builder without saving to avoid intermediate
 * dirty states that would re-trigger navigation blockers.
 */
export function resetAll() {
  useWorkflowStore.setState({
    currentWorkflow: null,
    projectId: null,
    edges: [],
    nodePositions: {},
    _positionsUserModified: false,
    isDirty: false,
    _undoBaselineMatchesSave: true,
    _nonTemporalDirty: false,
    validationErrorCount: 0,
  })
  useWorkflowStore.temporal.getState().clear()
}
