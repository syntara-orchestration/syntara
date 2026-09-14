import { EdgeHandleEnum } from '@syntara/contracts'
import { useEffect, useRef, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from 'react'

import { useWorkflowStore } from '../../../stores/useWorkflowStore'
import { toPositionKey } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { FlowPosition } from '../types'
import { LOOP_BODY_SPACING } from '../utils/layoutConstants'
import type { EdgeType } from '../utils/workflowToGraph'

type UseNodePositioningParams = {
  nodes: NodeType[]
  edges: EdgeType[]
  isInitialized: boolean
  newlyAddedNodeIdsRef: RefObject<Set<string>>
  containerRef: RefObject<HTMLDivElement | null>
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  getViewport: () => { x: number; y: number; zoom: number }
  updateNode: (nodeId: string, updates: { position: { x: number; y: number } }) => void
  /** Persist positions to the Zustand store (with skipTracking to avoid extra undo entries). */
  updateNodePositions: (
    positions: Record<string, { x: number; y: number }>,
    options?: { skipTracking?: boolean; markDirty?: boolean }
  ) => void
  /** When set, place the next new node's left edge at this position (e.g. from [+] click or pending edge drop) */
  desiredPosition: FlowPosition | null
  /** Called after desiredPosition has been applied so it can be cleared */
  onClearDesiredPosition?: () => void
}

/** Returns top-left position so the node's vertical center is at desired.y */
function positionWithCenterAt(desired: FlowPosition, height: number): FlowPosition {
  return { x: desired.x, y: desired.y - height / 2 }
}

function applyPositionedNodes(
  positionedNodes: Map<string, NodeType>,
  updateNode: (nodeId: string, updates: { position: { x: number; y: number } }) => void
) {
  positionedNodes.forEach((node, nodeId) => {
    updateNode(nodeId, { position: node.position })
  })
}

type PositionLoopNodeOptions = {
  node: NodeType
  newlyAddedNodeIdsRef: RefObject<Set<string>>
  baseX: number
  baseY: number
  loopPositions: Map<string, { x: number; y: number; width: number; height: number }>
  positionedNodes: Map<string, NodeType>
  overridePosition: FlowPosition | null
}

function positionLoopNode(options: PositionLoopNodeOptions): NodeType {
  const { node, newlyAddedNodeIdsRef, baseX, baseY, loopPositions, positionedNodes, overridePosition } = options

  if (
    newlyAddedNodeIdsRef.current.has(node.id) &&
    node.measured &&
    node.position.x === 0 &&
    node.position.y === 0 &&
    node.type === 'loop'
  ) {
    const loopWidth = node.measured?.width ?? 240
    const loopHeight = node.measured?.height ?? 0
    const position = overridePosition ?? { x: baseX, y: baseY }
    const loopPosData = { x: position.x, y: position.y, width: loopWidth, height: loopHeight }
    loopPositions.set(node.id, loopPosData)
    newlyAddedNodeIdsRef.current.delete(node.id)
    const updatedNode = { ...node, position }
    positionedNodes.set(node.id, updatedNode)
    return updatedNode
  }
  return node
}

function positionLoopBodyNode(
  node: NodeType,
  newlyAddedNodeIdsRef: RefObject<Set<string>>,
  loopBodyNodeMap: Map<string, string>,
  loopPositions: Map<string, { x: number; y: number; width: number; height: number }>,
  positionedNodes: Map<string, NodeType>
): NodeType {
  if (!newlyAddedNodeIdsRef.current.has(node.id) || !node.measured || !loopBodyNodeMap.has(node.id)) {
    return node
  }
  // eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- safe: loopBodyNodeMap.has(node.id) is checked in the early-return guard above (line 85)
  const loopNodeId = loopBodyNodeMap.get(node.id)!
  const loopPos = loopPositions.get(loopNodeId)
  if (!loopPos) return node

  // Position to the right and below the loop node, using unified spacing constants
  const calculatedX = loopPos.x + loopPos.width + LOOP_BODY_SPACING.horizontal
  const calculatedY = loopPos.y + LOOP_BODY_SPACING.vertical

  newlyAddedNodeIdsRef.current.delete(node.id)
  const updatedNode = { ...node, position: { x: calculatedX, y: calculatedY } }
  positionedNodes.set(node.id, updatedNode)
  return updatedNode
}

type LoopPositioningContext = {
  nodesToPosition: NodeType[]
  newlyAddedNodeIdsRef: RefObject<Set<string>>
  loopBodyNodeMap: Map<string, string>
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  getViewport: () => { x: number; y: number; zoom: number }
  updateNode: (nodeId: string, updates: { position: { x: number; y: number } }) => void
  updateNodePositions: UseNodePositioningParams['updateNodePositions']
  triggers: Array<{ id: string }>
  desiredPosition: FlowPosition | null
  onClearDesiredPosition?: () => void
  loopPositionTimerRef: MutableRefObject<ReturnType<typeof setTimeout> | null>
}

function positionLoopBranch(ctx: LoopPositioningContext) {
  const {
    nodesToPosition,
    newlyAddedNodeIdsRef,
    loopBodyNodeMap,
    setNodes,
    getViewport,
    updateNode,
    loopPositionTimerRef,
  } = ctx
  const viewport = getViewport()
  const padding = 50
  const baseX = (-viewport.x + padding) / viewport.zoom
  const baseY = (-viewport.y + padding) / viewport.zoom

  const firstLoopNode = nodesToPosition.find((n) => n.type === 'loop')
  const desiredLoopPosition =
    firstLoopNode && ctx.desiredPosition != null
      ? positionWithCenterAt(ctx.desiredPosition, firstLoopNode.measured?.height ?? 0)
      : null

  const loopBranchPositions: Record<string, { x: number; y: number }> = {}
  const clearDesiredAfterUpdate = { should: false }

  setNodes((currentNodes) => {
    const loopPositions = new Map<string, { x: number; y: number; width: number; height: number }>()
    const positionedNodes = new Map<string, NodeType>()
    const overrideForFirstLoop =
      firstLoopNode && desiredLoopPosition ? { nodeId: firstLoopNode.id, position: desiredLoopPosition } : null

    const updatedNodes = currentNodes.map((node) => {
      const overridePosition = node.id === overrideForFirstLoop?.nodeId ? overrideForFirstLoop.position : null
      const loopPositioned = positionLoopNode({
        node,
        newlyAddedNodeIdsRef,
        baseX,
        baseY,
        loopPositions,
        positionedNodes,
        overridePosition,
      })
      if (loopPositioned !== node) return loopPositioned
      return positionLoopBodyNode(node, newlyAddedNodeIdsRef, loopBodyNodeMap, loopPositions, positionedNodes)
    })

    const nodesChanged = updatedNodes.some((node, index) => node !== currentNodes[index])
    if (!nodesChanged && positionedNodes.size === 0) {
      clearDesiredAfterUpdate.should = false
      return currentNodes
    }

    clearDesiredAfterUpdate.should =
      ctx.desiredPosition != null && (overrideForFirstLoop != null || positionedNodes.size > 0)

    if (positionedNodes.size > 0) {
      positionedNodes.forEach((node, nodeId) => {
        loopBranchPositions[nodeId] = node.position
      })
      if (loopPositionTimerRef.current !== null) clearTimeout(loopPositionTimerRef.current)
      loopPositionTimerRef.current = setTimeout(() => {
        loopPositionTimerRef.current = null
        applyPositionedNodes(positionedNodes, updateNode)
      }, 100)
    }

    return updatedNodes
  })

  if (Object.keys(loopBranchPositions).length > 0) {
    const storePositions: Record<string, { x: number; y: number }> = {}
    for (const [id, pos] of Object.entries(loopBranchPositions)) {
      storePositions[toPositionKey(id, ctx.triggers)] = pos
    }
    ctx.updateNodePositions(storePositions, { skipTracking: true, markDirty: false })
  }

  if (clearDesiredAfterUpdate.should) {
    ctx.onClearDesiredPosition?.()
  }
}

type StandardPositioningContext = {
  nodesToPosition: NodeType[]
  newlyAddedNodeIdsRef: RefObject<Set<string>>
  containerRef: RefObject<HTMLDivElement | null>
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  getViewport: () => { x: number; y: number; zoom: number }
  updateNodePositions: UseNodePositioningParams['updateNodePositions']
  triggers: Array<{ id: string }>
  desiredPosition: FlowPosition | null
  onClearDesiredPosition?: () => void
}

function positionStandardNodes(ctx: StandardPositioningContext) {
  const { nodesToPosition, newlyAddedNodeIdsRef, containerRef, setNodes, getViewport } = ctx
  const viewport = getViewport()
  const viewportWidth = containerRef.current?.clientWidth ?? window.innerWidth
  const padding = 50
  const viewportX = (-viewport.x + viewportWidth - 350 - padding) / viewport.zoom
  const viewportY = (-viewport.y + padding) / viewport.zoom
  const firstNodeId = nodesToPosition[0]?.id

  const positionsToApply: Record<string, { x: number; y: number }> = {}
  for (const node of nodesToPosition) {
    if (ctx.desiredPosition != null && node.id === firstNodeId) {
      positionsToApply[node.id] = positionWithCenterAt(ctx.desiredPosition, node.measured?.height ?? 0)
    } else {
      positionsToApply[node.id] = { x: viewportX, y: viewportY }
    }
  }

  const nodesToPositionSet = new Set(nodesToPosition.map((n) => n.id))

  setNodes((currentNodes) =>
    currentNodes.map((node) => {
      const position = positionsToApply[node.id]
      if (!position || !nodesToPositionSet.has(node.id)) return node
      newlyAddedNodeIdsRef.current.delete(node.id)
      return { ...node, position }
    })
  )

  // Map React Flow display IDs to definition IDs for consistent store keys
  const storePositions: Record<string, { x: number; y: number }> = {}
  for (const [id, pos] of Object.entries(positionsToApply)) {
    storePositions[toPositionKey(id, ctx.triggers)] = pos
  }
  ctx.updateNodePositions(storePositions, { skipTracking: true, markDirty: false })

  if (ctx.desiredPosition != null && firstNodeId) {
    ctx.onClearDesiredPosition?.()
  }
}

function buildLoopBodyNodeMap(edges: EdgeType[]): Map<string, string> {
  const loopBodyNodeMap = new Map<string, string>()
  edges.forEach((e) => {
    if (e.sourceHandle === EdgeHandleEnum.LOOP) {
      loopBodyNodeMap.set(e.target, e.source)
    }
  })
  return loopBodyNodeMap
}

/**
 * Custom hook to handle positioning of newly added nodes in the workflow canvas.
 *
 * Handles two positioning strategies:
 * 1. Loop nodes and their body nodes - positioned on left side of viewport with proper spacing
 * 2. Regular nodes - positioned on right side of viewport
 *
 * Loop body nodes are identified by edges with sourceHandle='loop' and positioned
 * relative to their parent loop node with consistent spacing.
 */
export function useNodePositioning({
  nodes,
  edges,
  isInitialized,
  newlyAddedNodeIdsRef,
  containerRef,
  setNodes,
  getViewport,
  updateNode,
  updateNodePositions,
  desiredPosition,
  onClearDesiredPosition,
}: UseNodePositioningParams) {
  const loopPositionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (newlyAddedNodeIdsRef.current.size === 0 || !isInitialized) return

    // Wait for next render to ensure useNodeUpdates has finished adding nodes to the DOM
    // This prevents React from batching our setNodes call with useNodeUpdates' setNodes
    const timeoutId = setTimeout(() => {
      const loopBodyNodeMap = buildLoopBodyNodeMap(edges)
      const triggers = useWorkflowStore.getState().currentWorkflow?.triggers ?? []

      const nodesToPosition = nodes.filter((node) => {
        if (!newlyAddedNodeIdsRef.current.has(node.id) || !node.measured) return false
        return node.position.x === 0 && node.position.y === 0
      })

      if (nodesToPosition.length === 0) return

      const hasLoopBodyNodes = nodesToPosition.some((n) => n.type === 'loop' || loopBodyNodeMap.has(n.id))

      if (hasLoopBodyNodes) {
        positionLoopBranch({
          nodesToPosition,
          newlyAddedNodeIdsRef,
          loopBodyNodeMap,
          setNodes,
          getViewport,
          updateNode,
          updateNodePositions,
          triggers,
          desiredPosition,
          onClearDesiredPosition,
          loopPositionTimerRef,
        })
      } else {
        positionStandardNodes({
          nodesToPosition,
          newlyAddedNodeIdsRef,
          containerRef,
          setNodes,
          getViewport,
          updateNodePositions,
          triggers,
          desiredPosition,
          onClearDesiredPosition,
        })
      }
    }, 0) // Wait for next tick

    return () => {
      clearTimeout(timeoutId)
      if (loopPositionTimerRef.current !== null) {
        clearTimeout(loopPositionTimerRef.current)
        loopPositionTimerRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, isInitialized, getViewport, setNodes, updateNodePositions, desiredPosition, onClearDesiredPosition])
}
