import type { Edge, Node } from '@xyflow/react'

import { getCanvasNodeIconDescriptor } from '../../../workflows/canvas/nodes/nodeIconResolver'
import type { NodeType } from '../../../workflows/canvas/nodes/NodeType'

import type { UpstreamNodeInfo } from './useUpstreamNodes'

export type AdjacentNodes = {
  upstream: UpstreamNodeInfo[]
  downstream: UpstreamNodeInfo[]
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

function toNodeInfo(node: Node): UpstreamNodeInfo {
  const data = node.data as { name?: string; type?: string; triggerType?: string } | undefined
  const { icon, id: iconId } = getCanvasNodeIconDescriptor({
    id: node.id,
    type: node.type,
    data: node.data as NodeType['data'],
  })
  return {
    id: node.id,
    name: data?.name,
    type: data?.type ?? data?.triggerType ?? node.type ?? 'unknown',
    icon,
    iconId,
  }
}

function resolveNodes(ids: string[], nodeMap: Map<string, UpstreamNodeInfo>): UpstreamNodeInfo[] {
  const nodes: UpstreamNodeInfo[] = []
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

function buildNeighborNodeLookup(neighborIds: string[], nodes: Node[]): Map<string, UpstreamNodeInfo> {
  const neededIds = new Set(neighborIds)
  const nodeInfoById = new Map<string, UpstreamNodeInfo>()

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
export function getAdjacentNodesFromFlow(nodeId: string, edges: Edge[], nodes: Node[]): AdjacentNodes {
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
