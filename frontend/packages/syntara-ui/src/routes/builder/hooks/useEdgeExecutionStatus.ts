import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeConnection } from '../types/edge'
import { isTerminalState } from '../utils/executionState/executionHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

import { executionStateEnricher } from './useBuilderFlowGraph'

type ProjectEdgeExecutionStatusOptions = {
  effectiveExecutionStatus: string | null
  currentWorkflow: WorkflowDefinition | null
  activityStates: Map<string, ActivityState>
  storedEdges: EdgeConnection[]
  isExecutionDetailView?: boolean
}

/** Derives execution status for visible edges without changing controlled edge state. */
export function projectEdgeExecutionStatus(
  edges: EdgeType[],
  {
    effectiveExecutionStatus,
    currentWorkflow,
    activityStates,
    storedEdges,
    isExecutionDetailView = false,
  }: ProjectEdgeExecutionStatusOptions
): EdgeType[] {
  const isActive = effectiveExecutionStatus !== null && !isTerminalState(effectiveExecutionStatus)
  const isTerminal = effectiveExecutionStatus !== null && isTerminalState(effectiveExecutionStatus)

  if (!isActive && !(isExecutionDetailView && isTerminal)) {
    let changed = false
    const clearedEdges = edges.map((edge) => {
      if (edge.data?.executionStatus == null) return edge
      changed = true
      return { ...edge, data: { ...edge.data, executionStatus: undefined } }
    })
    return changed ? clearedEdges : edges
  }

  const activities = currentWorkflow?.workflow.activities ?? []
  const triggers = currentWorkflow?.triggers ?? []
  const triggerDisplayToRealId = new Map(triggers.map((trigger, index) => [buildTriggerNodeId(index), trigger.id]))
  let changed = false

  const projectedEdges = edges.map((edge) => {
    const executionStatus = executionStateEnricher.determineEdgeStatus({
      edge,
      activityStates,
      activities,
      triggerDisplayToRealId,
      edges: storedEdges,
    })
    if (edge.data?.executionStatus === executionStatus) return edge

    changed = true
    return { ...edge, data: { ...edge.data, executionStatus } }
  })

  return changed ? projectedEdges : edges
}
