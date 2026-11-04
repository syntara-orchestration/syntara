import { EdgeHandleEnum, type SwitchConfig } from '@syntara/contracts'

import { FlowNodeType } from '../../../constants'
import type { ButtonEdgePlaceholderNode, NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { OnAddNodeFromEdge, PendingEdge } from '../types'
import { filterRealNodes, isRealEdge } from '../utils/filterHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

import {
  createButtonEdgePlaceholderNode,
  mergeNewPlaceholderNodes,
  processMultiHandleNode,
} from './buttonEdgeMaintenanceHelpers'
import { computeNextButtonEdges, updateNodesForButtonEdgeClasses } from './computeButtonEdgesUpdate'

type MultiHandleConfig = {
  handles: readonly string[]
  handlePositions: Record<string, { yOffset: number; xOffset?: number }>
}

const MULTI_HANDLE_CONFIGS: Record<string, MultiHandleConfig> = {
  [FlowNodeType.CONDITION]: {
    handles: [EdgeHandleEnum.TRUE, EdgeHandleEnum.FALSE],
    handlePositions: {
      [EdgeHandleEnum.TRUE]: { yOffset: -30 },
      [EdgeHandleEnum.FALSE]: { yOffset: 30 },
    },
  },
  [FlowNodeType.APPROVAL]: {
    handles: [EdgeHandleEnum.APPROVED, EdgeHandleEnum.REJECTED],
    handlePositions: {
      [EdgeHandleEnum.APPROVED]: { yOffset: -30 },
      [EdgeHandleEnum.REJECTED]: { yOffset: 30 },
    },
  },
  [FlowNodeType.LOOP]: {
    handles: [EdgeHandleEnum.DONE, EdgeHandleEnum.LOOP],
    handlePositions: {
      [EdgeHandleEnum.DONE]: { yOffset: -30 },
      [EdgeHandleEnum.LOOP]: { yOffset: 30 },
    },
  },
}

type ButtonEdgeProjectionOptions = {
  nodes: NodeType[]
  edges: EdgeType[]
  isInitialized: boolean
  activeEdgeButtonNodeId: string | null
  activeEdgeButtonHandle: string | null
  onAddNodeFromEdge?: OnAddNodeFromEdge
  pendingEdge: PendingEdge | null
  executionStatus: string | null
  isReadOnly?: boolean
}

type ButtonEdgePlan = {
  nodesNeedingButtonEdges: string[]
  conditionHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  loopHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  approvalHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  switchHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  placeholderNodesToAdd: ButtonEdgePlaceholderNode[]
  connectedHandles: Map<string, Set<string>>
}

function buildConnectedHandlesMap(edges: EdgeType[]): Map<string, Set<string>> {
  const connectedHandles = new Map<string, Set<string>>()
  for (const edge of edges) {
    if (!isRealEdge(edge)) continue
    const handle = edge.sourceHandle ?? EdgeHandleEnum.SOURCE
    let handleSet = connectedHandles.get(edge.source)
    if (!handleSet) {
      handleSet = new Set()
      connectedHandles.set(edge.source, handleSet)
    }
    handleSet.add(handle)
  }
  return connectedHandles
}

function processSwitchNode(options: {
  node: NodeType
  connectedHandles: Map<string, Set<string>>
  pendingEdge: PendingEdge | null
  nodes: NodeType[]
  handlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  placeholderNodesToAdd: ButtonEdgePlaceholderNode[]
}) {
  const { node, connectedHandles, pendingEdge, nodes, handlesNeedingButtonEdges, placeholderNodesToAdd } = options
  const config = ((node.data as Record<string, unknown>).parameters ?? { cases: [] }) as SwitchConfig
  const handles = [...(config.cases ?? []).map((item) => item.port), EdgeHandleEnum.DEFAULT]
  const handlePositions: Record<string, { yOffset: number }> = {}
  const totalHandles = handles.length
  handles.forEach((handle, index) => {
    handlePositions[handle] = { yOffset: (index - (totalHandles - 1) / 2) * 40 }
  })
  processMultiHandleNode({
    node,
    handles,
    handlePositions,
    connectedHandles,
    pendingEdge,
    nodes,
    handlesNeedingButtonEdges,
    placeholderNodesToAdd,
  })
}

function buildButtonEdgePlan(nodes: NodeType[], edges: EdgeType[], pendingEdge: PendingEdge | null): ButtonEdgePlan {
  const realNodes = filterRealNodes(nodes)
  const realEdges = edges.filter(isRealEdge)
  const connectedHandles = buildConnectedHandlesMap(realEdges)
  const nodesNeedingButtonEdges: string[] = []
  const placeholderNodesToAdd: ButtonEdgePlaceholderNode[] = []
  const conditionHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[] = []
  const loopHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[] = []
  const approvalHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[] = []
  const switchHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[] = []
  const handleListsByNodeType: Record<string, { nodeId: string; handleId: string }[]> = {
    [FlowNodeType.CONDITION]: conditionHandlesNeedingButtonEdges,
    [FlowNodeType.LOOP]: loopHandlesNeedingButtonEdges,
    [FlowNodeType.APPROVAL]: approvalHandlesNeedingButtonEdges,
  }

  for (const node of realNodes) {
    const multiHandleConfig = node.type ? MULTI_HANDLE_CONFIGS[node.type] : undefined
    if (multiHandleConfig && node.type) {
      processMultiHandleNode({
        node,
        handles: multiHandleConfig.handles,
        handlePositions: multiHandleConfig.handlePositions,
        connectedHandles,
        pendingEdge,
        nodes: realNodes,
        handlesNeedingButtonEdges: handleListsByNodeType[node.type],
        placeholderNodesToAdd,
      })
      continue
    }

    if (node.type === FlowNodeType.SWITCH) {
      processSwitchNode({
        node,
        connectedHandles,
        pendingEdge,
        nodes: realNodes,
        handlesNeedingButtonEdges: switchHandlesNeedingButtonEdges,
        placeholderNodesToAdd,
      })
      continue
    }

    const sourceHandleConnected = connectedHandles.get(node.id)?.has(EdgeHandleEnum.SOURCE) ?? false
    const hasPendingEdge = pendingEdge?.sourceNodeId === node.id
    if (sourceHandleConnected || hasPendingEdge) continue

    nodesNeedingButtonEdges.push(node.id)
    placeholderNodesToAdd.push(
      createButtonEdgePlaceholderNode({
        id: `placeholder-${node.id}`,
        position: { x: node.position.x + 200, y: node.position.y },
      })
    )
  }

  return {
    nodesNeedingButtonEdges,
    conditionHandlesNeedingButtonEdges,
    loopHandlesNeedingButtonEdges,
    approvalHandlesNeedingButtonEdges,
    switchHandlesNeedingButtonEdges,
    placeholderNodesToAdd,
    connectedHandles,
  }
}

function cleanButtonEdgeClassNames(nodes: NodeType[]): NodeType[] {
  return updateNodesForButtonEdgeClasses(nodes, {
    nodesNeedingButtonEdges: [],
    conditionHandlesNeedingButtonEdges: [],
    loopHandlesNeedingButtonEdges: [],
    approvalHandlesNeedingButtonEdges: [],
    switchHandlesNeedingButtonEdges: [],
    connectedHandles: new Map(),
  })
}

/** Derives button edges, placeholders, and their node classes for the canvas. */
export function projectButtonEdgeMaintenance({
  nodes,
  edges,
  isInitialized,
  activeEdgeButtonNodeId,
  activeEdgeButtonHandle,
  onAddNodeFromEdge,
  pendingEdge,
  executionStatus,
  isReadOnly,
}: ButtonEdgeProjectionOptions): { nodes: NodeType[]; edges: EdgeType[] } {
  if (!isInitialized) return { nodes, edges }

  const realNodes = filterRealNodes(nodes)
  const realEdges = edges.filter(isRealEdge)
  if (executionStatus || isReadOnly) {
    return { nodes: cleanButtonEdgeClassNames(realNodes), edges: realEdges }
  }

  const plan = buildButtonEdgePlan(realNodes, realEdges, pendingEdge)
  const projectedEdges = computeNextButtonEdges({
    currentEdges: realEdges,
    conditionHandlesNeedingButtonEdges: plan.conditionHandlesNeedingButtonEdges,
    loopHandlesNeedingButtonEdges: plan.loopHandlesNeedingButtonEdges,
    approvalHandlesNeedingButtonEdges: plan.approvalHandlesNeedingButtonEdges,
    switchHandlesNeedingButtonEdges: plan.switchHandlesNeedingButtonEdges,
    nodesNeedingButtonEdges: plan.nodesNeedingButtonEdges,
    activeEdgeButtonNodeId,
    activeEdgeButtonHandle,
    onAddNodeFromEdge,
  })
  const projectedNodes = updateNodesForButtonEdgeClasses(realNodes, {
    nodesNeedingButtonEdges: plan.nodesNeedingButtonEdges,
    conditionHandlesNeedingButtonEdges: plan.conditionHandlesNeedingButtonEdges,
    loopHandlesNeedingButtonEdges: plan.loopHandlesNeedingButtonEdges,
    approvalHandlesNeedingButtonEdges: plan.approvalHandlesNeedingButtonEdges,
    switchHandlesNeedingButtonEdges: plan.switchHandlesNeedingButtonEdges,
    connectedHandles: plan.connectedHandles,
  })

  return {
    nodes: mergeNewPlaceholderNodes(plan.placeholderNodesToAdd, projectedNodes),
    edges: projectedEdges,
  }
}
