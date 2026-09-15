import { useReactFlow, type OnNodeDrag } from '@xyflow/react'
import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from 'react'

import { FlowNodeType } from '../../../constants'
import {
  useWorkflowStore,
  useWorkflowStoreActions,
  selectCurrentWorkflow,
  selectPositionUndoVersion,
} from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import { toPositionKey } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { filterRealEdges, filterRealNodes } from '../utils/filterHelpers'
import { getLayoutedElements } from '../utils/layoutEngine'
import { getLoopBodyMap } from '../utils/loopUtils'
import type { EdgeType } from '../utils/workflowToGraph'

type LoopDragState = {
  loopNodeId: string
  /** Offsets of non-selected body nodes relative to the loop node at drag start */
  offsets: Map<string, { dx: number; dy: number }>
}

export function usePositionEventHandlers(
  nodes: NodeType[],
  edges: EdgeType[],
  setNodes: Dispatch<SetStateAction<NodeType[]>>,
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
) {
  const currentWorkflow = useWorkflowStore(selectCurrentWorkflow)
  const positionUndoVersion = useWorkflowStore(selectPositionUndoVersion)
  const { updateNodePositions } = useWorkflowStoreActions()
  const { fitView } = useReactFlow<NodeType, EdgeType>()

  const positionUndoVersionRef = useRef(positionUndoVersion)
  useEffect(() => {
    if (positionUndoVersion === positionUndoVersionRef.current) return
    positionUndoVersionRef.current = positionUndoVersion
    const positions = useWorkflowStore.getState().nodePositions
    if (Object.keys(positions).length === 0) return
    const trigs = currentWorkflow?.triggers ?? []
    setNodes((prev) =>
      prev.map((n) => {
        const stored = positions[toPositionKey(n.id, trigs)]
        return stored ? { ...n, position: stored } : n
      })
    )
  }, [positionUndoVersion, currentWorkflow?.triggers, setNodes])

  const loopDragRef = useRef<LoopDragState | null>(null)

  const onNodeDragStart = useCallback(
    (_event: Parameters<OnNodeDrag<NodeType>>[0], node: NodeType, draggedNodes: NodeType[]) => {
      if (node.type !== FlowNodeType.LOOP) {
        loopDragRef.current = null
        return
      }
      const bodyMap = getLoopBodyMap(filterRealNodes(nodes), filterRealEdges(edges), { includeDoneBranch: true })
      const bodyNodeIds = bodyMap.get(node.id)
      if (!bodyNodeIds || bodyNodeIds.length === 0) {
        loopDragRef.current = null
        return
      }
      // Only track body nodes that aren't already being dragged by React Flow (multi-select case)
      const draggedNodeIds = new Set(draggedNodes.map((n) => n.id))
      const offsets = new Map<string, { dx: number; dy: number }>()
      for (const bodyId of bodyNodeIds) {
        if (draggedNodeIds.has(bodyId)) continue
        const bodyNode = nodes.find((n) => n.id === bodyId)
        if (bodyNode) {
          offsets.set(bodyId, {
            dx: bodyNode.position.x - node.position.x,
            dy: bodyNode.position.y - node.position.y,
          })
        }
      }
      if (offsets.size === 0) {
        loopDragRef.current = null
        return
      }
      loopDragRef.current = { loopNodeId: node.id, offsets }
    },
    [nodes, edges]
  )

  const onNodeDrag = useCallback(
    (_event: Parameters<OnNodeDrag<NodeType>>[0], node: NodeType) => {
      if (loopDragRef.current?.loopNodeId !== node.id) return
      const { offsets } = loopDragRef.current
      setNodes((prev) =>
        prev.map((n) => {
          const offset = offsets.get(n.id)
          if (!offset) return n
          return { ...n, position: { x: node.position.x + offset.dx, y: node.position.y + offset.dy } }
        })
      )
    },
    [setNodes]
  )

  const onNodeDragStop = useCallback(
    (_event: Parameters<OnNodeDrag<NodeType>>[0], node: NodeType, draggedNodes: NodeType[]) => {
      if (draggedNodes.length === 0) return
      const trigs = currentWorkflow?.triggers ?? []
      const positions: Record<string, { x: number; y: number }> = Object.fromEntries(
        draggedNodes.map((n) => [toPositionKey(n.id, trigs), n.position])
      )
      // Include body nodes moved during loop group drag using offsets captured at drag start.
      // This avoids relying on React Flow's getNodes() being flushed before drag stop.
      // Require node.id so `undefined === undefined` cannot match when loopDrag is null.
      const loopDrag = loopDragRef.current
      if (node.id && loopDrag?.loopNodeId === node.id) {
        for (const [bodyId, offset] of loopDrag.offsets) {
          positions[toPositionKey(bodyId, trigs)] = {
            x: node.position.x + offset.dx,
            y: node.position.y + offset.dy,
          }
        }
        loopDragRef.current = null
      }
      updateNodePositions(positions)
    },
    [updateNodePositions, currentWorkflow?.triggers]
  )

  const onLayout = useCallback(
    ({ markDirty = false }: { markDirty?: boolean } = {}) => {
      const layouted = getLayoutedElements(nodes, edges, { direction: 'LR' })
      setNodes([...layouted.nodes])
      setEdges([...layouted.edges] as EdgeType[])
      const trigs = currentWorkflow?.triggers ?? []
      const positions: Record<string, { x: number; y: number }> = {}
      for (const n of layouted.nodes) positions[toPositionKey(n.id, trigs)] = n.position
      updateNodePositions(positions, { skipTracking: !markDirty, markDirty })
      detachPromise(fitView({ maxZoom: 1 }))
    },
    [nodes, edges, setNodes, setEdges, fitView, updateNodePositions, currentWorkflow?.triggers]
  )

  return { onNodeDragStart, onNodeDrag, onNodeDragStop, onLayout }
}
