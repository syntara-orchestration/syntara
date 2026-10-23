import type { Edge, Node } from '@xyflow/react'

import { getCanvasStepIconDescriptor } from '../../../workflows/canvas/nodes/stepIconResolver'

import type { UpstreamStepInfo } from './useUpstreamSteps'

export type AdjacentSteps = {
  upstream: UpstreamStepInfo[]
  downstream: UpstreamStepInfo[]
}

function isNavigableNodeId(nodeId: string): boolean {
  return !nodeId.startsWith('placeholder-') && !nodeId.startsWith('pending-target-')
}

function isRealFlowEdge(edge: Edge): boolean {
  return edge.type !== 'buttonEdge' && !edge.id.startsWith('button-') && !edge.id.startsWith('pending-')
}

function isNavigableFlowEdge(edge: Edge): boolean {
  return isRealFlowEdge(edge) && isNavigableNodeId(edge.source) && isNavigableNodeId(edge.target)
}

function toNodeInfo(node: Node): UpstreamStepInfo {
  const data = node.data as { name?: string; type?: string; triggerType?: string } | undefined
  const { icon, id: iconId } = getCanvasStepIconDescriptor({
    id: node.id,
    type: node.type,
    data: node.data,
  })
  return {
    id: node.id,
    name: data?.name,
    type: data?.type ?? data?.triggerType ?? node.type ?? 'unknown',
    icon,
    iconId,
  }
}

function resolveNodes(ids: string[], nodeMap: Map<string, UpstreamStepInfo>): UpstreamStepInfo[] {
  const nodes: UpstreamStepInfo[] = []
  for (const id of ids) {
    const node = nodeMap.get(id)
    if (node) {
      nodes.push(node)
    }
  }
  return nodes
}

type NeighborIds = {
  upstreamOrder: string[]
  downstreamOrder: string[]
}

function collectNeighborIds(nodeId: string, edges: Edge[]): NeighborIds {
  const upstreamIds = new Set<string>()
  const downstreamIds = new Set<string>()
  const upstreamOrder: string[] = []
  const downstreamOrder: string[] = []

  for (const edge of edges) {
    if (!isNavigableFlowEdge(edge)) continue

    if (edge.target === nodeId && edge.source !== nodeId && !upstreamIds.has(edge.source)) {
      upstreamIds.add(edge.source)
      upstreamOrder.push(edge.source)
    }
    if (edge.source === nodeId && edge.target !== nodeId && !downstreamIds.has(edge.target)) {
      downstreamIds.add(edge.target)
      downstreamOrder.push(edge.target)
    }
  }

  return { upstreamOrder, downstreamOrder }
}

function buildNeighborNodeLookup(neighborIds: string[], nodes: Node[]): Map<string, UpstreamStepInfo> {
  const neededIds = new Set(neighborIds)
  const nodeInfoById = new Map<string, UpstreamStepInfo>()

  for (const node of nodes) {
    if (!neededIds.has(node.id) || !isNavigableNodeId(node.id)) continue

    nodeInfoById.set(node.id, toNodeInfo(node))
    if (nodeInfoById.size === neededIds.size) break
  }

  return nodeInfoById
}

/**
 * Returns direct upstream/downstream neighbors using React Flow graph IDs — the same
 * edge/node model used by canvas interactions and test-step predecessor traversal.
 */
export function getAdjacentStepsFromFlow(nodeId: string, edges: Edge[], nodes: Node[]): AdjacentSteps {
  const { upstreamOrder, downstreamOrder } = collectNeighborIds(nodeId, edges)

  if (upstreamOrder.length === 0 && downstreamOrder.length === 0) {
    return { upstream: [], downstream: [] }
  }

  const nodeInfoById = buildNeighborNodeLookup([...upstreamOrder, ...downstreamOrder], nodes)

  return {
    upstream: resolveNodes(upstreamOrder, nodeInfoById),
    downstream: resolveNodes(downstreamOrder, nodeInfoById),
  }
}
