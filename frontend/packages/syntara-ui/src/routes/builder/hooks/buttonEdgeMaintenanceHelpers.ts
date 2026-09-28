import { EdgeHandleEnum } from '@syntara/contracts'

import { FlowNodeType } from '../../../constants'
import type { ButtonEdgePlaceholderNode, NodeType } from '../../workflows/canvas/nodes/NodeType'
import { isSwitchCasePort } from '../utils/switchCaseHelpers'

export type HandlePositionConfig = {
  yOffset: number
  xOffset?: number
}

export function createButtonEdgePlaceholderNode(params: {
  id: string
  position: { x: number; y: number }
}): ButtonEdgePlaceholderNode {
  return {
    id: params.id,
    type: FlowNodeType.PLACEHOLDER,
    position: params.position,
    data: {},
    draggable: false,
    selectable: false,
  }
}

export type ProcessMultiHandleNodeOptions = {
  node: NodeType
  handles: readonly string[]
  handlePositions: Record<string, HandlePositionConfig>
  connectedHandles: Map<string, Set<string>>
  pendingEdge: { sourceNodeId: string; sourceHandle?: string } | null
  nodes: NodeType[]
  handlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  placeholderNodesToAdd: ButtonEdgePlaceholderNode[]
}

export function processMultiHandleNode(options: ProcessMultiHandleNodeOptions) {
  const {
    node,
    handles,
    handlePositions,
    connectedHandles,
    pendingEdge,
    nodes,
    handlesNeedingButtonEdges,
    placeholderNodesToAdd,
  } = options
  handles.forEach((handleId) => {
    const handleConnected = connectedHandles.get(node.id)?.has(handleId) ?? false
    const hasPendingEdge = pendingEdge?.sourceNodeId === node.id && pendingEdge?.sourceHandle === handleId

    if (!handleConnected && !hasPendingEdge) {
      handlesNeedingButtonEdges.push({ nodeId: node.id, handleId })

      const placeholderId = `placeholder-${node.id}-${handleId}`
      const placeholderExists = nodes.some((n) => n.id === placeholderId)

      if (!placeholderExists) {
        const positionConfig = handlePositions[handleId]
        const yOffset = positionConfig.yOffset
        const xOffset = positionConfig.xOffset ?? 200
        placeholderNodesToAdd.push(
          createButtonEdgePlaceholderNode({
            id: placeholderId,
            position: { x: node.position.x + xOffset, y: node.position.y + yOffset },
          })
        )
      }
    }
  })
}

export function mergeNewPlaceholderNodes(
  placeholders: ButtonEdgePlaceholderNode[],
  currentNodes: NodeType[]
): NodeType[] {
  const existingIds = new Set(currentNodes.map((n) => n.id))
  const nodesToAdd = placeholders.filter((n) => !existingIds.has(n.id))
  return nodesToAdd.length > 0 ? [...currentNodes, ...nodesToAdd] : currentNodes
}

export type ButtonEdgeFilterContext = {
  conditionHandles: { nodeId: string; handleId: string }[]
  loopHandles: { nodeId: string; handleId: string }[]
  approvalHandles: { nodeId: string; handleId: string }[]
  switchHandles: { nodeId: string; handleId: string }[]
  regularNodeIds: string[]
  activeNodeId: string | null
  activeHandle: string | null
}

function isSwitchHandleId(handleId: string | null | undefined): boolean {
  return handleId === EdgeHandleEnum.DEFAULT || isSwitchCasePort(handleId)
}

function keepIfNeeded<T extends { source: string; sourceHandle?: string | null; data?: Record<string, unknown> }>(
  edge: T,
  handles: { nodeId: string; handleId: string }[],
  ctx: ButtonEdgeFilterContext
): (T & { data: Record<string, unknown> }) | null {
  const isNeeded = handles.some((h) => h.nodeId === edge.source && h.handleId === edge.sourceHandle)
  if (!isNeeded) return null
  return {
    ...edge,
    data: {
      ...edge.data,
      isActive: ctx.activeNodeId === edge.source && ctx.activeHandle === edge.sourceHandle,
    },
  }
}

const HANDLE_TO_CONTEXT_KEY: Record<
  string,
  keyof Pick<ButtonEdgeFilterContext, 'conditionHandles' | 'loopHandles' | 'approvalHandles'>
> = {
  [EdgeHandleEnum.TRUE]: 'conditionHandles',
  [EdgeHandleEnum.FALSE]: 'conditionHandles',
  [EdgeHandleEnum.DONE]: 'loopHandles',
  [EdgeHandleEnum.LOOP]: 'loopHandles',
  [EdgeHandleEnum.APPROVED]: 'approvalHandles',
  [EdgeHandleEnum.REJECTED]: 'approvalHandles',
}

export function getKeptButtonEdge<
  T extends { source: string; sourceHandle?: string | null; data?: Record<string, unknown> },
>(edge: T, ctx: ButtonEdgeFilterContext): (T & { data: Record<string, unknown> }) | null {
  const handleId = edge.sourceHandle

  const ctxKey = handleId ? HANDLE_TO_CONTEXT_KEY[handleId] : undefined
  if (ctxKey) {
    return keepIfNeeded(edge, ctx[ctxKey], ctx)
  }

  if (isSwitchHandleId(handleId)) {
    return keepIfNeeded(edge, ctx.switchHandles, ctx)
  }

  if ((handleId === EdgeHandleEnum.SOURCE || !handleId) && ctx.regularNodeIds.includes(edge.source)) {
    return {
      ...edge,
      data: {
        ...edge.data,
        isActive: ctx.activeNodeId === edge.source && (ctx.activeHandle === EdgeHandleEnum.SOURCE || !ctx.activeHandle),
      },
    }
  }

  return null
}
