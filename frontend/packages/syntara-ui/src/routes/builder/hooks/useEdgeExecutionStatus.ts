import type { Dispatch, SetStateAction } from 'react'
import { useEffect, useRef } from 'react'

import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import { buildTriggerNodeId } from '../../../utils/triggerNodeIds'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeConnection } from '../types/edge'
import { isTerminalState } from '../utils/executionState/executionHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

import { executionStateEnricher } from './useBuilderFlowGraph'

type UseEdgeExecutionStatusOptions = {
  effectiveExecutionStatus: string | null
  isInitialized: boolean
  currentWorkflow: WorkflowDefinition | null
  activityStates: Map<string, ActivityState>
  storedEdges: EdgeConnection[]
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  isExecutionDetailView?: boolean
}

export function useEdgeExecutionStatus({
  effectiveExecutionStatus,
  isInitialized,
  currentWorkflow,
  activityStates,
  storedEdges,
  setEdges,
  isExecutionDetailView = false,
}: UseEdgeExecutionStatusOptions) {
  const prevExecutionStatusRef = useRef(effectiveExecutionStatus)

  useEffect(() => {
    const prev = prevExecutionStatusRef.current
    prevExecutionStatusRef.current = effectiveExecutionStatus

    const wasActive = prev !== null && !isTerminalState(prev)
    const isActive = effectiveExecutionStatus !== null && !isTerminalState(effectiveExecutionStatus)
    const isTerminal = effectiveExecutionStatus !== null && isTerminalState(effectiveExecutionStatus)

    // Cleanup: clear edge statuses when execution becomes inactive (active → terminal/null transition).
    // Skip cleanup in execution detail view — preserve edge statuses for completed runs.
    if (wasActive && !isActive && isInitialized && !isExecutionDetailView) {
      setEdges((edges) => {
        if (!edges.some((e) => e.data?.executionStatus != null)) return edges
        return edges.map((e) =>
          e.data?.executionStatus != null ? { ...e, data: { ...e.data, executionStatus: undefined } } : e
        )
      })
      return
    }

    // Enrichment: set edge statuses during active execution or in execution detail view for completed runs.
    if ((!isActive && !(isExecutionDetailView && isTerminal)) || !isInitialized) return

    const activities = currentWorkflow?.workflow.activities ?? []
    const triggers = currentWorkflow?.triggers ?? []
    const triggerDisplayToRealId = new Map(triggers.map((t, i) => [buildTriggerNodeId(i), t.id]))

    setEdges((currentEdges) =>
      currentEdges.map((edge) => {
        const edgeExecutionStatus = executionStateEnricher.determineEdgeStatus({
          edge: edge,
          activityStates: activityStates,
          activities: activities,
          triggerDisplayToRealId: triggerDisplayToRealId,
          edges: storedEdges,
        })

        if (edge.data?.executionStatus !== edgeExecutionStatus) {
          return {
            ...edge,
            data: {
              ...edge.data,
              executionStatus: edgeExecutionStatus,
            },
          }
        }

        return edge
      })
    )
  }, [
    activityStates,
    effectiveExecutionStatus,
    isInitialized,
    currentWorkflow,
    storedEdges,
    setEdges,
    isExecutionDetailView,
  ])
}
