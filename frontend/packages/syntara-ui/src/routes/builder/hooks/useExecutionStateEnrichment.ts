import { useCallback, useEffect } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'

import { executionStateEnricher } from './useBuilderFlowGraph'

type ExecutionStateSnapshot = {
  status?: string
  started_at?: string
  completed_at?: string
}

type UseExecutionStateEnrichmentParams = {
  effectiveExecutionStatus: string | null
  isInitialized: boolean
  currentWorkflow: WorkflowDefinition | null
  activityStates: Map<string, ActivityState>
  preResolvedNodes: Set<string>
  copiedRunActivityIds?: ReadonlySet<string> | null
  setNodes: React.Dispatch<React.SetStateAction<NodeType[]>>
}

function hasExecutionStateChanged(
  currentState: ExecutionStateSnapshot | undefined,
  newState: ExecutionStateSnapshot | undefined
): boolean {
  return (
    currentState !== newState &&
    (currentState?.status !== newState?.status ||
      currentState?.started_at !== newState?.started_at ||
      currentState?.completed_at !== newState?.completed_at)
  )
}

function applyEnrichedData(
  node: NodeType,
  enriched: Record<string, unknown>,
  anyChangedRef: { current: boolean }
): NodeType {
  const currentState = (node.data as Record<string, unknown>).__executionState as ExecutionStateSnapshot | undefined
  const newState = enriched.__executionState as ExecutionStateSnapshot | undefined
  if (hasExecutionStateChanged(currentState, newState)) {
    anyChangedRef.current = true
    return { ...node, data: enriched } as unknown as NodeType
  }
  return node
}

/**
 * Enriches canvas nodes with execution state during execution view, and clears
 * execution overlays when returning to edit mode.
 */
export function useExecutionStateEnrichment({
  effectiveExecutionStatus,
  isInitialized,
  currentWorkflow,
  activityStates,
  preResolvedNodes,
  copiedRunActivityIds,
  setNodes,
}: UseExecutionStateEnrichmentParams): void {
  const applyEnrichedDataStable = useCallback(
    (node: NodeType, enriched: Record<string, unknown>, anyChangedRef: { current: boolean }) =>
      applyEnrichedData(node, enriched, anyChangedRef),
    []
  )

  useEffect(() => {
    if (!isInitialized) return

    if (!effectiveExecutionStatus) {
      setNodes((currentNodes) => {
        const hasExecutionState = currentNodes.some((node) => (node.data as Record<string, unknown>).__executionState)
        if (!hasExecutionState) return currentNodes

        return currentNodes.map((node) => {
          const currentData = node.data as Record<string, unknown>
          if (!currentData.__executionState) return node
          const rest = Object.fromEntries(Object.entries(currentData).filter(([key]) => key !== '__executionState'))
          return { ...node, data: rest } as unknown as NodeType
        })
      })
      return
    }

    if (activityStates.size === 0) return

    const activities = currentWorkflow?.workflow.activities ?? []
    const triggers = currentWorkflow?.triggers ?? []
    const activitiesById = new Map(activities.map((activity) => [activity.id, activity]))
    const edgeSnapshot = useWorkflowStore.getState().edges

    setNodes((currentNodes) => {
      const anyChangedRef = { current: false }
      const updatedNodes = currentNodes.map((node) => {
        if (node.id.startsWith('trigger-')) {
          const triggerRealId = triggers[Number.parseInt(node.id.split('-')[1], 10)]?.id
          const enriched = executionStateEnricher.enrichTriggerNode(
            triggerRealId,
            node.data as Record<string, unknown>,
            effectiveExecutionStatus,
            activityStates
          )
          return applyEnrichedDataStable(node, enriched, anyChangedRef)
        }
        const activity = activitiesById.get(node.id)
        if (!activity) return node
        const enriched = executionStateEnricher.enrichActivity(
          activity,
          effectiveExecutionStatus,
          activityStates,
          edgeSnapshot,
          { preResolvedNodes, skipInferenceActivityIds: copiedRunActivityIds ?? undefined }
        )
        return applyEnrichedDataStable(node, enriched, anyChangedRef)
      })

      return anyChangedRef.current ? updatedNodes : currentNodes
    })
  }, [
    activityStates,
    effectiveExecutionStatus,
    isInitialized,
    currentWorkflow,
    applyEnrichedDataStable,
    preResolvedNodes,
    copiedRunActivityIds,
    setNodes,
  ])
}
