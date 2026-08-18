import { EdgeHandleEnum } from '@syntara/contracts'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { FlowPosition } from '../types'
import { isSwitchCasePort } from '../utils/switchCaseHelpers'
import type { EdgeType } from '../utils/workflowToGraph'

import { type ButtonEdgeFilterContext, getKeptButtonEdge } from './buttonEdgeMaintenanceHelpers'

export type ComputeButtonEdgesParams = {
  currentEdges: EdgeType[]
  conditionHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  loopHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  approvalHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  switchHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  nodesNeedingButtonEdges: string[]
  activeEdgeButtonNodeId: string | null
  activeEdgeButtonHandle: string | null
  onAddNodeFromEdge?: (
    sourceNodeId: string,
    targetNodeId?: string,
    edgeId?: string,
    sourceHandle?: string,
    desiredPosition?: FlowPosition
  ) => void
}

function createOnButtonClick(
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge'],
  nodeId: string,
  handleId: string
): (pos: FlowPosition | undefined) => void {
  return (pos: FlowPosition | undefined) => {
    onAddNodeFromEdge?.(nodeId, undefined, undefined, handleId, pos)
  }
}

function isExistingButtonEdge(edge: EdgeType): boolean {
  return edge.type === 'buttonEdge' || edge.id.startsWith('button-')
}

function partitionEdgesByButtonKind(currentEdges: EdgeType[]): {
  nonButtonEdges: EdgeType[]
  existingButtonEdges: EdgeType[]
} {
  const nonButtonEdges: EdgeType[] = []
  const existingButtonEdges: EdgeType[] = []
  for (const edge of currentEdges) {
    if (isExistingButtonEdge(edge)) {
      existingButtonEdges.push(edge)
    } else {
      nonButtonEdges.push(edge)
    }
  }
  return { nonButtonEdges, existingButtonEdges }
}

type ButtonHandleKeySets = {
  /** Sources that already have a button edge (any handle); used to skip duplicate regular SOURCE edges. */
  nodesWithRegularButtonEdge: Set<string>
  conditionKeys: Set<string>
  loopKeys: Set<string>
  approvalKeys: Set<string>
  switchKeys: Set<string>
}

const HANDLE_TO_KEY_SET: Record<string, 'conditionKeys' | 'loopKeys' | 'approvalKeys'> = {
  [EdgeHandleEnum.TRUE]: 'conditionKeys',
  [EdgeHandleEnum.FALSE]: 'conditionKeys',
  [EdgeHandleEnum.DONE]: 'loopKeys',
  [EdgeHandleEnum.LOOP]: 'loopKeys',
  [EdgeHandleEnum.APPROVED]: 'approvalKeys',
  [EdgeHandleEnum.REJECTED]: 'approvalKeys',
}

function buildButtonHandleKeySets(existingButtonEdges: EdgeType[]): ButtonHandleKeySets {
  const nodesWithRegularButtonEdge = new Set<string>()
  const conditionKeys = new Set<string>()
  const loopKeys = new Set<string>()
  const approvalKeys = new Set<string>()
  const switchKeys = new Set<string>()

  const keySets = { conditionKeys, loopKeys, approvalKeys }

  for (const edge of existingButtonEdges) {
    const handle = edge.sourceHandle
    const key = `${edge.source}-${handle}`

    const setName = handle ? HANDLE_TO_KEY_SET[handle] : undefined
    if (setName) {
      keySets[setName].add(key)
    } else if (handle === EdgeHandleEnum.DEFAULT || isSwitchCasePort(handle)) {
      switchKeys.add(key)
    } else if (handle === EdgeHandleEnum.SOURCE || handle == null || handle === '') {
      nodesWithRegularButtonEdge.add(edge.source)
    }
  }

  return { nodesWithRegularButtonEdge, conditionKeys, loopKeys, approvalKeys, switchKeys }
}

/** Tracks which `onAddNodeFromEdge` the edge's click handler was built with (in-memory only). */
const BUTTON_EDGE_BOUND_ON_ADD = '__syntaraButtonEdgeBoundOnAdd' as const

function collectKeptButtonEdges(
  existingButtonEdges: EdgeType[],
  ctx: ButtonEdgeFilterContext,
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge']
): EdgeType[] {
  const kept: EdgeType[] = []
  for (const edge of existingButtonEdges) {
    const next = getKeptButtonEdge(edge, ctx)
    if (!next) {
      continue
    }
    const prevData = edge.data as Record<string, unknown>
    const boundOnAdd = prevData[BUTTON_EDGE_BOUND_ON_ADD]
    const needsNewHandler = boundOnAdd !== onAddNodeFromEdge || next.data?.onButtonClick == null
    const handleId = next.sourceHandle ?? EdgeHandleEnum.SOURCE
    const data = next.data as Record<string, unknown>
    const onButtonClick = needsNewHandler
      ? createOnButtonClick(onAddNodeFromEdge, next.source, handleId)
      : (data.onButtonClick as (pos: FlowPosition | undefined) => void)
    kept.push({
      ...next,
      data: {
        ...data,
        onButtonClick,
        [BUTTON_EDGE_BOUND_ON_ADD]: onAddNodeFromEdge,
      },
    } as unknown as EdgeType)
  }
  return kept
}

function buildRegularNodeButtonEdge(
  nodeId: string,
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge'],
  activeNodeId: string | null,
  activeHandle: string | null
): EdgeType {
  const buttonEdgeId = `button-${nodeId}`
  const placeholderId = `placeholder-${nodeId}`
  return {
    id: buttonEdgeId,
    source: nodeId,
    sourceHandle: EdgeHandleEnum.SOURCE,
    target: placeholderId,
    targetHandle: EdgeHandleEnum.TARGET,
    type: 'buttonEdge',
    selectable: false,
    data: {
      sourceNodeId: nodeId,
      sourceHandle: EdgeHandleEnum.SOURCE,
      onButtonClick: createOnButtonClick(onAddNodeFromEdge, nodeId, EdgeHandleEnum.SOURCE),
      isActive: activeNodeId === nodeId && (activeHandle === EdgeHandleEnum.SOURCE || !activeHandle),
    },
  } as unknown as EdgeType
}

function buildMultiHandleButtonEdge(
  nodeId: string,
  handleId: string,
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge'],
  activeNodeId: string | null,
  activeHandle: string | null
): EdgeType {
  const buttonEdgeId = `button-${nodeId}-${handleId}`
  const placeholderId = `placeholder-${nodeId}-${handleId}`
  return {
    id: buttonEdgeId,
    source: nodeId,
    sourceHandle: handleId,
    target: placeholderId,
    targetHandle: EdgeHandleEnum.TARGET,
    type: 'buttonEdge',
    selectable: false,
    data: {
      sourceNodeId: nodeId,
      sourceHandle: handleId,
      onButtonClick: createOnButtonClick(onAddNodeFromEdge, nodeId, handleId),
      isActive: activeNodeId === nodeId && activeHandle === handleId,
    },
  } as unknown as EdgeType
}

type AppendMissingRegularButtonEdgesOptions = {
  nodeIds: string[]
  nodesWithButtonEdge: Set<string>
  buttonEdgesToAdd: EdgeType[]
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge']
  activeNodeId: string | null
  activeHandle: string | null
}

function appendMissingRegularButtonEdges(options: AppendMissingRegularButtonEdgesOptions): void {
  const { nodeIds, nodesWithButtonEdge, buttonEdgesToAdd, onAddNodeFromEdge, activeNodeId, activeHandle } = options
  for (const nodeId of nodeIds) {
    if (nodesWithButtonEdge.has(nodeId)) {
      continue
    }
    buttonEdgesToAdd.push(buildRegularNodeButtonEdge(nodeId, onAddNodeFromEdge, activeNodeId, activeHandle))
  }
}

type AppendMissingMultiHandleButtonEdgesOptions = {
  handles: { nodeId: string; handleId: string }[]
  existingKeys: Set<string>
  buttonEdgesToAdd: EdgeType[]
  onAddNodeFromEdge: ComputeButtonEdgesParams['onAddNodeFromEdge']
  activeNodeId: string | null
  activeHandle: string | null
}

function appendMissingMultiHandleButtonEdges(options: AppendMissingMultiHandleButtonEdgesOptions): void {
  const { handles, existingKeys, buttonEdgesToAdd, onAddNodeFromEdge, activeNodeId, activeHandle } = options
  for (const { nodeId, handleId } of handles) {
    const key = `${nodeId}-${handleId}`
    if (existingKeys.has(key)) {
      continue
    }
    buttonEdgesToAdd.push(buildMultiHandleButtonEdge(nodeId, handleId, onAddNodeFromEdge, activeNodeId, activeHandle))
  }
}

function anyKeptButtonEdgeChanged(existingButtonEdges: EdgeType[], buttonEdgesToKeep: EdgeType[]): boolean {
  const existingById = new Map(existingButtonEdges.map((e) => [e.id, e]))
  return buttonEdgesToKeep.some((edge) => {
    const previous = existingById.get(edge.id)
    if (!previous) {
      return true
    }
    const p = previous.data as { isActive?: boolean; onButtonClick?: unknown }
    const n = edge.data as { isActive?: boolean; onButtonClick?: unknown }
    return p.isActive !== n.isActive || p.onButtonClick !== n.onButtonClick
  })
}

function shouldReturnNewEdgeList(
  currentEdges: EdgeType[],
  result: EdgeType[],
  buttonEdgesToAdd: EdgeType[],
  existingButtonEdges: EdgeType[],
  buttonEdgesToKeep: EdgeType[]
): boolean {
  if (result.length !== currentEdges.length || buttonEdgesToAdd.length > 0) {
    return true
  }
  return anyKeptButtonEdgeChanged(existingButtonEdges, buttonEdgesToKeep)
}

/**
 * Computes the next edge list after button-edge maintenance (add/remove/update placeholders).
 * Extracted from the hook so nested callbacks do not exceed maintainability limits.
 */
export function computeNextButtonEdges(params: ComputeButtonEdgesParams): EdgeType[] {
  const {
    currentEdges,
    conditionHandlesNeedingButtonEdges,
    loopHandlesNeedingButtonEdges,
    approvalHandlesNeedingButtonEdges,
    switchHandlesNeedingButtonEdges,
    nodesNeedingButtonEdges,
    activeEdgeButtonNodeId,
    activeEdgeButtonHandle,
    onAddNodeFromEdge,
  } = params

  const { nonButtonEdges, existingButtonEdges } = partitionEdgesByButtonKind(currentEdges)
  const keySets = buildButtonHandleKeySets(existingButtonEdges)

  const buttonEdgeCtx: ButtonEdgeFilterContext = {
    conditionHandles: conditionHandlesNeedingButtonEdges,
    loopHandles: loopHandlesNeedingButtonEdges,
    approvalHandles: approvalHandlesNeedingButtonEdges,
    switchHandles: switchHandlesNeedingButtonEdges,
    regularNodeIds: nodesNeedingButtonEdges,
    activeNodeId: activeEdgeButtonNodeId,
    activeHandle: activeEdgeButtonHandle,
  }

  const buttonEdgesToKeep = collectKeptButtonEdges(existingButtonEdges, buttonEdgeCtx, onAddNodeFromEdge)
  const buttonEdgesToAdd: EdgeType[] = []

  const activeCtx = {
    onAddNodeFromEdge,
    activeNodeId: activeEdgeButtonNodeId,
    activeHandle: activeEdgeButtonHandle,
  }

  appendMissingRegularButtonEdges({
    nodeIds: nodesNeedingButtonEdges,
    nodesWithButtonEdge: keySets.nodesWithRegularButtonEdge,
    buttonEdgesToAdd,
    ...activeCtx,
  })
  appendMissingMultiHandleButtonEdges({
    handles: conditionHandlesNeedingButtonEdges,
    existingKeys: keySets.conditionKeys,
    buttonEdgesToAdd,
    ...activeCtx,
  })
  appendMissingMultiHandleButtonEdges({
    handles: loopHandlesNeedingButtonEdges,
    existingKeys: keySets.loopKeys,
    buttonEdgesToAdd,
    ...activeCtx,
  })
  appendMissingMultiHandleButtonEdges({
    handles: approvalHandlesNeedingButtonEdges,
    existingKeys: keySets.approvalKeys,
    buttonEdgesToAdd,
    ...activeCtx,
  })
  appendMissingMultiHandleButtonEdges({
    handles: switchHandlesNeedingButtonEdges,
    existingKeys: keySets.switchKeys,
    buttonEdgesToAdd,
    ...activeCtx,
  })

  const result = [...nonButtonEdges, ...buttonEdgesToKeep, ...buttonEdgesToAdd]

  if (!shouldReturnNewEdgeList(currentEdges, result, buttonEdgesToAdd, existingButtonEdges, buttonEdgesToKeep)) {
    return currentEdges
  }

  return result
}

export type UpdateNodesButtonEdgeClassParams = {
  nodesNeedingButtonEdges: string[]
  conditionHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  loopHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  approvalHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  switchHandlesNeedingButtonEdges: { nodeId: string; handleId: string }[]
  connectedHandles: Map<string, Set<string>>
}

type ButtonEdgeClassLookup = {
  regularNodeIds: Set<string>
  conditionNodeIds: Set<string>
  loopNodeIds: Set<string>
  approvalNodeIds: Set<string>
  switchNodeIds: Set<string>
}

function buildButtonEdgeClassLookup(params: UpdateNodesButtonEdgeClassParams): ButtonEdgeClassLookup {
  return {
    regularNodeIds: new Set(params.nodesNeedingButtonEdges),
    conditionNodeIds: new Set(params.conditionHandlesNeedingButtonEdges.map((h) => h.nodeId)),
    loopNodeIds: new Set(params.loopHandlesNeedingButtonEdges.map((h) => h.nodeId)),
    approvalNodeIds: new Set(params.approvalHandlesNeedingButtonEdges.map((h) => h.nodeId)),
    switchNodeIds: new Set(params.switchHandlesNeedingButtonEdges.map((h) => h.nodeId)),
  }
}

function nodeNeedsButtonEdgeClass(
  nodeId: string,
  nodeType: string | undefined,
  lookup: ButtonEdgeClassLookup
): boolean {
  if (lookup.regularNodeIds.has(nodeId)) {
    return true
  }
  if (nodeType === FlowNodeType.CONDITION) {
    return lookup.conditionNodeIds.has(nodeId)
  }
  if (nodeType === FlowNodeType.LOOP) {
    return lookup.loopNodeIds.has(nodeId)
  }
  if (nodeType === FlowNodeType.APPROVAL) {
    return lookup.approvalNodeIds.has(nodeId)
  }
  if (nodeType === FlowNodeType.SWITCH) {
    return lookup.switchNodeIds.has(nodeId)
  }
  return false
}

function appendConnectedHandleClasses(className: string, connectedHandlesForNode: Set<string>): string {
  let next = className
  for (const handleId of connectedHandlesForNode) {
    next = `${next} handle-${handleId}-connected`.trim()
  }
  return next
}

/**
 * Updates node className for button-edge styling after edges are synchronized.
 */
export function updateNodesForButtonEdgeClasses(
  currentNodes: NodeType[],
  params: UpdateNodesButtonEdgeClassParams
): NodeType[] {
  const lookup = buildButtonEdgeClassLookup(params)
  return currentNodes.map((node) => {
    if (node.id.startsWith('pending-target-')) {
      return node
    }

    const shouldHaveButtonEdge = nodeNeedsButtonEdgeClass(node.id, node.type, lookup)
    const currentClassName = node.className ?? ''

    let newClassName = currentClassName
      .replaceAll(/\bhas-button-edge\b/g, '')
      .replaceAll(/\bhandle-\w+-connected\b/g, '')
      .trim()

    if (shouldHaveButtonEdge) {
      newClassName = `${newClassName} has-button-edge`.trim()
    }

    const connectedHandlesForNode = params.connectedHandles.get(node.id)
    if (connectedHandlesForNode && connectedHandlesForNode.size > 0) {
      newClassName = appendConnectedHandleClasses(newClassName, connectedHandlesForNode)
    }

    if (newClassName !== currentClassName) {
      return { ...node, className: newClassName }
    }
    return node
  })
}
