import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'
import type { EdgeConnection } from '../types/edge'

import { executionStateEnricher } from './useBuilderFlowGraph'

type ExecutionStateSnapshot = {
  status?: string
  started_at?: string
  completed_at?: string
}

type ProjectExecutionStateOptions = {
  effectiveExecutionStatus: string | null
  currentWorkflow: WorkflowDefinition | null
  activityStates: Map<string, ActivityState>
  storedEdges: EdgeConnection[]
  preResolvedNodes: Set<string>
  copiedRunActivityIds?: ReadonlySet<string> | null
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

function withEnrichedExecutionState(
  node: NodeType,
  enriched: Record<string, unknown>,
  changed: { current: boolean }
): NodeType {
  const currentData = node.data as Record<string, unknown>
  const currentState = currentData.__executionState as ExecutionStateSnapshot | undefined
  const newState = enriched.__executionState as ExecutionStateSnapshot | undefined
  const currentMetadata = currentData.metadata as Record<string, unknown> | undefined
  const newMetadata = enriched.metadata as Record<string, unknown> | undefined
  const executionMetadataChanged =
    currentMetadata?.__showExecutionBadge !== newMetadata?.__showExecutionBadge ||
    currentMetadata?.__mockDataPinned !== newMetadata?.__mockDataPinned
  if (!hasExecutionStateChanged(currentState, newState) && !executionMetadataChanged) return node

  changed.current = true
  return { ...node, data: enriched } as unknown as NodeType
}

/** Derives execution overlays for visible nodes without changing controlled node state. */
export function projectExecutionState(
  nodes: NodeType[],
  {
    effectiveExecutionStatus,
    currentWorkflow,
    activityStates,
    storedEdges,
    preResolvedNodes,
    copiedRunActivityIds,
  }: ProjectExecutionStateOptions
): NodeType[] {
  if (!effectiveExecutionStatus) {
    let changed = false
    const clearedNodes = nodes.map((node) => {
      const currentData = node.data as Record<string, unknown>
      const currentMetadata = currentData.metadata as Record<string, unknown> | undefined
      const hasExecutionOverlay =
        currentData.__executionState !== undefined ||
        currentMetadata?.__showExecutionBadge !== undefined ||
        currentMetadata?.__mockDataPinned !== undefined
      if (!hasExecutionOverlay) return node
      changed = true
      const data = Object.fromEntries(Object.entries(currentData).filter(([key]) => key !== '__executionState'))
      if (currentMetadata) {
        const metadata = Object.fromEntries(
          Object.entries(currentMetadata).filter(
            ([key]) => key !== '__showExecutionBadge' && key !== '__mockDataPinned'
          )
        )
        if (Object.keys(metadata).length > 0) data.metadata = metadata
        else delete data.metadata
      }
      return { ...node, data } as unknown as NodeType
    })
    return changed ? clearedNodes : nodes
  }

  const activities = currentWorkflow?.workflow.activities ?? []
  const triggers = currentWorkflow?.triggers ?? []
  const activitiesById = new Map(activities.map((activity) => [activity.id, activity]))
  const changed = { current: false }

  const projectedNodes = nodes.map((node) => {
    if (node.id.startsWith('trigger-')) {
      const triggerIndex = Number.parseInt(node.id.slice('trigger-'.length), 10)
      const triggerRealId = triggers[triggerIndex]?.id
      const enriched = executionStateEnricher.enrichTriggerNode(
        triggerRealId,
        node.data,
        effectiveExecutionStatus,
        activityStates
      )
      return withEnrichedExecutionState(node, enriched, changed)
    }

    const activity = activitiesById.get(node.id)
    if (!activity) return node
    const enriched = executionStateEnricher.enrichActivity({
      activity,
      executionStatus: effectiveExecutionStatus,
      activityStates,
      edges: storedEdges,
      options: { preResolvedNodes, skipInferenceActivityIds: copiedRunActivityIds ?? undefined },
    })
    return withEnrichedExecutionState(node, enriched, changed)
  })

  return changed.current ? projectedNodes : nodes
}
