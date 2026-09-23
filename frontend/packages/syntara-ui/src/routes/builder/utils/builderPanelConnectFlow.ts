import { EdgeHandleEnum } from '@syntara/contracts'
import type { Node, ReactFlowInstance } from '@xyflow/react'

import { FlowNodeType } from '../../../constants'
import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { FlowPosition } from '../types'

import { EdgeFactory } from './EdgeFactory'
import { isSwitchCasePort } from './switchCaseHelpers'
import type { EdgeType } from './workflowToGraph'

const PANEL_CONNECT_MAX_ATTEMPTS = 40
const PANEL_CONNECT_RETRY_MS = 50

// v8 ignore start — React Flow wiring; covered by builder E2E / integration flows

function hasConditionNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some(
    (n) =>
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.TRUE}` ||
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.FALSE}`
  )
}

function hasLoopNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some(
    (n) =>
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.DONE}` ||
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.LOOP}`
  )
}

function hasApprovalNodePlaceholders(nodes: Node[], sourceId: string): boolean {
  return nodes.some(
    (n) =>
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.APPROVED}` ||
      n.id === `placeholder-${sourceId}-${EdgeHandleEnum.REJECTED}`
  )
}

function removeButtonEdgeClass(nodes: Node[], sourceId: string): Node[] {
  return nodes.map((n) => {
    if (n.id === sourceId) {
      const className = (n.className ?? '').replace('has-button-edge', '').trim()
      return { ...n, className }
    }
    return n
  })
}

function applyFirstEdgeAfterPanelConnect(
  eds: EdgeType[],
  sourceId: string,
  capturedSourceHandle: string | undefined,
  capturedEdgeIdToReplace: string | null | undefined,
  newEdge: EdgeType
): EdgeType[] {
  const filtered = EdgeFactory.removeButtonEdge(sourceId, eds, capturedSourceHandle)
  const withoutOldEdge = capturedEdgeIdToReplace ? filtered.filter((e) => e.id !== capturedEdgeIdToReplace) : filtered
  return EdgeFactory.addEdge(newEdge, withoutOldEdge)
}

function updateNodesAfterPanelConnect(nds: Node[], sourceId: string, sourcePlaceholderId: string): Node[] {
  const filtered = nds.filter((n) => n.id !== sourcePlaceholderId)
  const sourceNode = filtered.find((n) => n.id === sourceId)
  if (!sourceNode) {
    return filtered
  }
  if (sourceNode.type === FlowNodeType.CONDITION && hasConditionNodePlaceholders(filtered, sourceId)) {
    return filtered
  }
  if (sourceNode.type === FlowNodeType.LOOP && hasLoopNodePlaceholders(filtered, sourceId)) {
    return filtered
  }
  if (sourceNode.type === FlowNodeType.APPROVAL && hasApprovalNodePlaceholders(filtered, sourceId)) {
    return filtered
  }
  return removeButtonEdgeClass(filtered, sourceId)
}

export type PanelConnectReactFlowAdapter = {
  getNodes: () => Node[]
  setEdges: (updater: (edges: EdgeType[]) => EdgeType[]) => void
  setNodes: (updater: (nodes: Node[]) => Node[]) => void
}

export type PanelConnectCapturedState = {
  sourceId: string
  targetId: string
  capturedSourceHandle: string | undefined | null
  capturedTargetHandle: string | undefined | null
  capturedEdgeIdToReplace: string | null | undefined
  capturedTargetNodeId: string | null | undefined
  onAddNodeFromEdge: (
    sourceId: string,
    targetId?: string,
    edgeId?: string,
    handle?: string,
    desiredPosition?: FlowPosition
  ) => void
}

/**
 * Bridges React Flow instance APIs into {@link PanelConnectReactFlowAdapter} (typed edges for our graph layer).
 */
export function createPanelConnectReactFlowAdapter(
  instance: Pick<ReactFlowInstance, 'getNodes' | 'setEdges' | 'setNodes'>
): PanelConnectReactFlowAdapter {
  return {
    getNodes: () => instance.getNodes(),
    setEdges: (updater) => {
      instance.setEdges((eds) => updater(eds as EdgeType[]))
    },
    setNodes: (updater) => {
      instance.setNodes((nds) => updater(nds))
    },
  }
}

type PendingPanelConnect = {
  attempts: number
  flow: PanelConnectReactFlowAdapter
  state: PanelConnectCapturedState
  cancelled: boolean
  timeoutId: ReturnType<typeof setTimeout> | undefined
}

/**
 * After the add-node panel connects two nodes, apply edges and cleanup once the target is measured.
 */
export function applyConnectFromPanelWhenTargetMeasured(
  flow: PanelConnectReactFlowAdapter,
  state: PanelConnectCapturedState
): void {
  const {
    sourceId,
    targetId,
    capturedSourceHandle: srcHandle,
    capturedTargetHandle,
    capturedEdgeIdToReplace,
    capturedTargetNodeId,
    onAddNodeFromEdge,
  } = state

  const sourceHandle = srcHandle ?? undefined

  const newEdge = EdgeFactory.createEdge({
    source: sourceId,
    target: targetId,
    sourceHandle,
    targetHandle: 'target',
    onAddNode: onAddNodeFromEdge,
  })

  flow.setEdges((eds) => applyFirstEdgeAfterPanelConnect(eds, sourceId, sourceHandle, capturedEdgeIdToReplace, newEdge))

  if (capturedEdgeIdToReplace && capturedTargetNodeId) {
    const secondEdge = EdgeFactory.createEdge({
      source: targetId,
      target: capturedTargetNodeId,
      sourceHandle: 'source',
      targetHandle: capturedTargetHandle ?? 'target',
      onAddNode: onAddNodeFromEdge,
    })
    flow.setEdges((eds) => EdgeFactory.addEdge(secondEdge, eds))
    useWorkflowStore.getState().moveActivityBefore(targetId, capturedTargetNodeId)
  }

  if (srcHandle === EdgeHandleEnum.LOOP && !capturedEdgeIdToReplace) {
    const loopBackEdge = EdgeFactory.createEdge({
      source: targetId,
      target: sourceId,
      sourceHandle: 'source',
      targetHandle: 'end',
      onAddNode: onAddNodeFromEdge,
    })
    flow.setEdges((eds) => EdgeFactory.addEdge(loopBackEdge, eds))
  }

  const isConditionHandle = srcHandle === EdgeHandleEnum.TRUE || srcHandle === EdgeHandleEnum.FALSE
  const isLoopHandle = srcHandle === EdgeHandleEnum.DONE || srcHandle === EdgeHandleEnum.LOOP
  const isApprovalHandle = srcHandle === EdgeHandleEnum.APPROVED || srcHandle === EdgeHandleEnum.REJECTED
  const isSwitchLikeHandle = isSwitchCasePort(srcHandle) || srcHandle === EdgeHandleEnum.DEFAULT
  const sourcePlaceholderId =
    isConditionHandle || isLoopHandle || isApprovalHandle || isSwitchLikeHandle
      ? `placeholder-${sourceId}-${srcHandle}`
      : `placeholder-${sourceId}`

  flow.setNodes((nds) => updateNodesAfterPanelConnect(nds, sourceId, sourcePlaceholderId))
}

function panelConnectRetryTick(pending: PendingPanelConnect): void {
  if (pending.cancelled) {
    return
  }
  const targetNode = pending.flow.getNodes().find((n) => n.id === pending.state.targetId)
  if (targetNode?.measured) {
    if (!pending.cancelled) {
      applyConnectFromPanelWhenTargetMeasured(pending.flow, pending.state)
    }
    return
  }
  if (pending.attempts >= PANEL_CONNECT_MAX_ATTEMPTS) {
    return
  }
  pending.attempts += 1
  pending.timeoutId = setTimeout(() => {
    pending.timeoutId = undefined
    panelConnectRetryTick(pending)
  }, PANEL_CONNECT_RETRY_MS)
}

/**
 * Waits until React Flow has measured the target node, then runs {@link applyConnectFromPanelWhenTargetMeasured}.
 * Returns a disposer that clears any pending timeout and prevents further retries (e.g. on unmount or a new connect).
 */
export function scheduleConnectFromPanelUntilMeasured(
  flow: PanelConnectReactFlowAdapter,
  state: PanelConnectCapturedState
): () => void {
  const pending: PendingPanelConnect = {
    attempts: 0,
    flow,
    state,
    cancelled: false,
    timeoutId: undefined,
  }
  panelConnectRetryTick(pending)
  return () => {
    pending.cancelled = true
    if (pending.timeoutId !== undefined) {
      clearTimeout(pending.timeoutId)
      pending.timeoutId = undefined
    }
  }
}

// v8 ignore stop
