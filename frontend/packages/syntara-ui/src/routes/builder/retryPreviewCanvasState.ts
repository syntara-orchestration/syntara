import { FlowNodeType } from '../../constants'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

export type RetryPreviewGraphEdge = Readonly<{ source: string; target: string }>
export type RetryPreviewCanvasNode = Readonly<{ id: string; type?: string; status?: string }>
export type RetryPreviewCanvasState = 'origin' | 'will-retry' | 'retained' | 'not-retried'

/** Find the workflow nodes that are downstream of the selected retry start points. */
function getRetryPreviewReachableNodeIds(
  retryPointIds: readonly string[],
  edges: readonly RetryPreviewGraphEdge[]
): Set<string> {
  const reachable = new Set(retryPointIds.map((pointId) => parseCompositeKey(pointId).baseId))
  const outgoing = new Map<string, string[]>()

  for (const edge of edges) {
    const targets = outgoing.get(edge.source) ?? []
    targets.push(edge.target)
    outgoing.set(edge.source, targets)
  }

  const queue = [...reachable]
  for (let index = 0; index < queue.length; index += 1) {
    const nodeId = queue[index]
    if (!nodeId) continue
    for (const targetId of outgoing.get(nodeId) ?? []) {
      if (reachable.has(targetId)) continue
      reachable.add(targetId)
      queue.push(targetId)
    }
  }

  return reachable
}

/** Classify source-run nodes for the retry preview without changing workflow or execution state. */
export function getRetryPreviewCanvasStates(
  nodes: readonly RetryPreviewCanvasNode[],
  edges: readonly RetryPreviewGraphEdge[],
  retryPointIds: readonly string[]
): Map<string, RetryPreviewCanvasState> {
  if (retryPointIds.length === 0) return new Map()

  const roots = new Set(retryPointIds.map((pointId) => parseCompositeKey(pointId).baseId))
  const reachable = getRetryPreviewReachableNodeIds(retryPointIds, edges)
  const states = new Map<string, RetryPreviewCanvasState>()

  for (const node of nodes) {
    if (node.type === FlowNodeType.TRIGGER || node.type === FlowNodeType.PLACEHOLDER) continue
    if (roots.has(node.id)) {
      states.set(node.id, 'origin')
    } else if (reachable.has(node.id)) {
      states.set(node.id, 'will-retry')
    } else if (node.status === 'completed') {
      states.set(node.id, 'retained')
    } else if (node.status === 'failed') {
      states.set(node.id, 'not-retried')
    }
  }

  return states
}

/** Count distinct failed workflow steps outside the selected retry paths. */
export function getNotRetriedFailureCount(
  failedActivityIds: readonly string[],
  retryPointIds: readonly string[],
  edges: readonly RetryPreviewGraphEdge[]
): number {
  const reachable = getRetryPreviewReachableNodeIds(retryPointIds, edges)
  const notRetried = new Set(
    failedActivityIds
      .map((activityId) => parseCompositeKey(activityId).baseId)
      .filter((activityId) => !reachable.has(activityId))
  )
  return notRetried.size
}
