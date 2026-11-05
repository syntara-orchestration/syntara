import { EdgeHandleEnum } from '@syntara/contracts'

import type { OnAddNodeFromEdge } from '../types'
import { markerEnd, type EdgeType } from '../utils/workflowToGraph'

type ProjectEdgeActiveStateOptions = {
  activeEdgeId: string | null
  activeEdgeButtonNodeId: string | null
  activeEdgeButtonHandle: string | null
  onAddNodeFromEdge?: OnAddNodeFromEdge
  isInitialized: boolean
}

const STANDARD_EDGE_TYPES = ['default', 'loopBack', 'loopOutgoing', 'loopDone']
const SPECIFIC_BUTTON_HANDLES = [
  EdgeHandleEnum.TRUE,
  EdgeHandleEnum.FALSE,
  EdgeHandleEnum.DONE,
  EdgeHandleEnum.LOOP,
  EdgeHandleEnum.APPROVED,
  EdgeHandleEnum.REJECTED,
] as const

function isStandardEdge(edge: EdgeType): boolean {
  return STANDARD_EDGE_TYPES.includes(edge.type ?? '')
}

function isButtonEdge(edge: EdgeType): boolean {
  return edge.type === 'buttonEdge' || edge.id.startsWith('button-')
}

function projectStandardEdge(
  edge: EdgeType,
  activeEdgeId: string | null,
  onAddNodeFromEdge: OnAddNodeFromEdge | undefined
): EdgeType {
  const isActive = activeEdgeId === edge.id || edge.data?.isPending
  const needsData = onAddNodeFromEdge !== undefined && edge.data?.onAddNode == null
  const needsMarker = !edge.markerEnd
  if (!needsData && !needsMarker && edge.data?.isActive === isActive) return edge

  return {
    ...edge,
    markerEnd: edge.markerEnd ?? markerEnd,
    data: {
      ...edge.data,
      ...(needsData ? { onAddNode: onAddNodeFromEdge } : {}),
      isActive,
    },
  }
}

function projectButtonEdge(
  edge: EdgeType,
  activeEdgeButtonNodeId: string | null,
  activeEdgeButtonHandle: string | null
): EdgeType {
  const dataSourceHandle = typeof edge.data?.sourceHandle === 'string' ? edge.data.sourceHandle : undefined
  const edgeHandle = dataSourceHandle ?? edge.sourceHandle ?? 'source'
  const isSpecificHandle = SPECIFIC_BUTTON_HANDLES.some((handle) => handle === edgeHandle)
  const matchesNode = activeEdgeButtonNodeId === edge.source
  const isActive = isSpecificHandle
    ? matchesNode && activeEdgeButtonHandle === edgeHandle
    : matchesNode && (activeEdgeButtonHandle === EdgeHandleEnum.SOURCE || !activeEdgeButtonHandle)

  if (edge.data?.isActive === isActive) return edge
  return { ...edge, data: { ...edge.data, isActive } }
}

/** Adds render-only active state and callbacks to workflow edges. */
export function projectEdgeActiveState(edges: EdgeType[], options: ProjectEdgeActiveStateOptions): EdgeType[] {
  const { activeEdgeId, activeEdgeButtonNodeId, activeEdgeButtonHandle, onAddNodeFromEdge, isInitialized } = options
  const projectedEdges = edges.map((edge) => {
    if (isStandardEdge(edge)) return projectStandardEdge(edge, activeEdgeId, onAddNodeFromEdge)
    if (isInitialized && isButtonEdge(edge)) {
      return projectButtonEdge(edge, activeEdgeButtonNodeId, activeEdgeButtonHandle)
    }
    return edge
  })

  return projectedEdges.some((edge, index) => edge !== edges[index]) ? projectedEdges : edges
}
