import { useWorkflowStore } from '../../stores/useWorkflowStore'

export function getWorkflowSnapshot() {
  const store = useWorkflowStore.getState()
  const currentWorkflow = store.currentWorkflow
  const activities = currentWorkflow?.workflow.activities ?? []
  const triggers = currentWorkflow?.triggers ?? []
  return { store, currentWorkflow, activities, triggers, edges: store.edges, nodePositions: store.nodePositions }
}
