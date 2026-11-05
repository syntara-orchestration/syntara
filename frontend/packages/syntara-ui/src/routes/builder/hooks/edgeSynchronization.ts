import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { parseTriggerIndex } from '../../../utils/triggerNodeIds'
import type { EdgeConnection } from '../types/edge'
import { isButtonEdge } from '../utils/filterHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

/** Returns the workflow edges represented by the live React Flow graph. */
export function getSynchronizedEdgeConnections(
  edges: EdgeType[],
  triggers: ReadonlyArray<{ id: string }>
): EdgeConnection[] {
  const realEdges = edges.filter(
    (edge) =>
      !isButtonEdge(edge) &&
      !edge.id.startsWith('pending-') &&
      !edge.source.startsWith('placeholder-') &&
      !edge.target.startsWith('placeholder-') &&
      !edge.source.startsWith('pending-target-') &&
      !edge.target.startsWith('pending-target-')
  )

  return realEdges.map((edge) => {
    let source = edge.source
    const sourceTriggerIndex = parseTriggerIndex(edge.source)
    if (sourceTriggerIndex !== undefined && triggers[sourceTriggerIndex]) {
      source = triggers[sourceTriggerIndex].id
    }

    let target = edge.target
    const targetTriggerIndex = parseTriggerIndex(edge.target)
    if (targetTriggerIndex !== undefined && triggers[targetTriggerIndex]) {
      target = triggers[targetTriggerIndex].id
    }

    return {
      id: edge.id,
      source,
      target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    }
  })
}

export type EdgeSynchronizationState = {
  lastEdgesSignature: string
  isSyncing: boolean
  isFirstSync: boolean
}

type SynchronizeBuilderFlowEdgesOptions = {
  edges: EdgeType[]
  isInitialized: boolean
  isActiveExecution: boolean
  state: EdgeSynchronizationState
  setStoredEdges: (edges: EdgeConnection[]) => void
}

/** Synchronizes BuilderFlow's live edges with the workflow store when needed. */
export function synchronizeBuilderFlowEdges({
  edges,
  isInitialized,
  isActiveExecution,
  state,
  setStoredEdges,
}: SynchronizeBuilderFlowEdgesOptions): void {
  if (!isInitialized || isActiveExecution || state.isSyncing) return

  const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []
  const edgeConnections = getSynchronizedEdgeConnections(edges, triggers)
  const currentSignature = JSON.stringify(edgeConnections)

  if (state.isFirstSync) {
    state.isFirstSync = false
    state.lastEdgesSignature = currentSignature
    return
  }

  if (currentSignature === state.lastEdgesSignature) return

  state.lastEdgesSignature = currentSignature
  setStoredEdges(edgeConnections)
  state.isSyncing = true
  useWorkflowStore.getState().reorderActivitiesFromEdges()

  if (useWorkflowStore.getState()._temporalBatchPending) {
    useWorkflowStore.setState({ _temporalBatchPending: false })
    useWorkflowStore.temporal.getState().resume()
  }

  queueMicrotask(() => {
    state.isSyncing = false
  })
}
