import { useReactFlow, type OnNodeDrag } from '@xyflow/react'
import { useCallback, useEffect, useRef, type Dispatch, type SetStateAction } from 'react'

import {
  useWorkflowStore,
  useWorkflowStoreActions,
  selectCurrentWorkflow,
  selectPositionUndoVersion,
} from '../../../stores/useWorkflowStore'
import { detachPromise } from '../../../utils/detachPromise'
import { toPositionKey } from '../../../utils/triggerNodeIds'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { getLayoutedElements } from '../utils/layoutEngine'
import type { EdgeType } from '../utils/workflowToGraph'

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

  const onNodeDragStop = useCallback(
    (_event: Parameters<OnNodeDrag<NodeType>>[0], _node: NodeType, draggedNodes: NodeType[]) => {
      if (draggedNodes.length === 0) return
      const trigs = currentWorkflow?.triggers ?? []
      updateNodePositions(Object.fromEntries(draggedNodes.map((n) => [toPositionKey(n.id, trigs), n.position])))
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

  return { onNodeDragStop, onLayout }
}
