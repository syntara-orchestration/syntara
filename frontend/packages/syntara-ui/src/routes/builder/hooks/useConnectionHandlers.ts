import { EdgeHandleEnum } from '@syntara/contracts'
import type { Connection, OnConnect } from '@xyflow/react'
import { useCallback, useRef, type Dispatch, type SetStateAction } from 'react'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ConnectionState, FlowPosition, PendingEdge } from '../types'
import { EdgeFactory } from '../utils/EdgeFactory'
import { getPlaceholderNodeId } from '../utils/edgeHelpers'
import { consumePendingDragHandle } from '../utils/pendingDragHandle'
import type { EdgeType } from '../utils/workflowToGraph'

type UseConnectionHandlersParams = {
  nodes: NodeType[]
  edges: EdgeType[]
  onAddNodeFromEdge?: (
    sourceNodeId: string,
    nodeType?: string,
    activityId?: string,
    sourceHandle?: string,
    desiredPosition?: FlowPosition
  ) => void
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  setPendingEdge: Dispatch<SetStateAction<PendingEdge | null>>
  screenToFlowPosition: (position: { x: number; y: number }) => { x: number; y: number }
}

export function useConnectionHandlers({
  nodes,
  edges,
  onAddNodeFromEdge,
  setNodes,
  setEdges,
  setPendingEdge,
  screenToFlowPosition,
}: UseConnectionHandlersParams) {
  const connectionStateRef = useRef<ConnectionState>({
    sourceNodeId: null,
    sourceHandleId: null,
    successful: false,
  })

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      // Guard against null source or target
      if (!connection.source || !connection.target) {
        return
      }

      connectionStateRef.current.successful = true

      setPendingEdge(null)

      // Detect if this connection is closing a loop
      // If the target is a loop node and the source is inside the loop body,
      // change targetHandle from 'target' to 'end'
      let targetHandle = connection.targetHandle ?? undefined
      const targetNode = nodes.find((n) => n.id === connection.target)

      if (targetNode?.type === FlowNodeType.LOOP && targetHandle === EdgeHandleEnum.TARGET) {
        // Check if source node is inside the loop body
        // A node is inside the loop body if there's a path from the loop's 'loop' handle to this node
        const loopEdges = edges.filter((e) => e.source === connection.target && e.sourceHandle === EdgeHandleEnum.LOOP)
        const loopBodyNodeIds = new Set<string>()

        // BFS to find all nodes reachable from the loop handle
        const queue = loopEdges.map((e) => e.target)
        const visited = new Set<string>()

        while (queue.length > 0) {
          const nodeId = queue[0]
          queue.shift()
          if (visited.has(nodeId)) continue
          visited.add(nodeId)
          loopBodyNodeIds.add(nodeId)

          // Find outgoing edges (but don't follow edges back to the loop's target handle)
          const outgoing = edges.filter(
            (e) => e.source === nodeId && !(e.target === connection.target && e.targetHandle === EdgeHandleEnum.TARGET)
          )
          queue.push(...outgoing.map((e) => e.target))
        }

        // If source is in the loop body, this is a loop-closing connection
        if (loopBodyNodeIds.has(connection.source)) {
          targetHandle = EdgeHandleEnum.END
        }
      }

      const newEdge = EdgeFactory.createEdge({
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle,
        onAddNode: onAddNodeFromEdge,
      })

      setEdges((eds) => {
        // Pass sourceHandle to remove the correct button edge (important for condition nodes)
        const updatedEdges = EdgeFactory.removeButtonEdge(connection.source, eds, connection.sourceHandle ?? undefined)
        return EdgeFactory.addEdge(newEdge, updatedEdges)
      })

      // Determine the placeholder ID based on whether this is a condition node handle
      const sourcePlaceholderId = getPlaceholderNodeId(connection.source, connection.sourceHandle ?? undefined)

      setNodes((nds) => {
        // Filter out the specific placeholder
        const filtered = nds.filter((n) => n.id !== sourcePlaceholderId)

        // Check if the source node still has any button edges (for condition nodes with multiple handles)
        const sourceNode = filtered.find((n) => n.id === connection.source)
        if (!sourceNode) return filtered

        // For condition nodes, only remove the class if both handles are connected
        const isConditionNode = sourceNode.type === FlowNodeType.CONDITION
        if (isConditionNode) {
          // Check if there are any remaining condition handle placeholders for this node
          const hasRemainingPlaceholders = filtered.some(
            (n) =>
              n.id === getPlaceholderNodeId(connection.source, EdgeHandleEnum.TRUE) ||
              n.id === getPlaceholderNodeId(connection.source, EdgeHandleEnum.FALSE)
          )
          if (hasRemainingPlaceholders) {
            // Keep the class since there are still button edges
            return filtered
          }
        }

        // Remove the has-button-edge class if no more button edges
        return filtered.map((n) => {
          if (n.id === connection.source) {
            const className = (n.className ?? '').replace('has-button-edge', '').trim()
            return { ...n, className }
          }
          return n
        })
      })
    },
    [setEdges, setNodes, onAddNodeFromEdge, nodes, edges, setPendingEdge]
  )

  const onConnectStart = useCallback(
    (_: unknown, params: { nodeId: string | null; handleId: string | null; handleType: string | null }) => {
      if (params.nodeId && params.handleType === 'source') {
        // Check if ButtonEdge set an intended handle ID (for condition node handles).
        // React Flow's handle detection can pick the wrong handle when handles overlap,
        // so we use the explicitly set handle ID if available.
        const pendingHandle = consumePendingDragHandle()
        const handleId = pendingHandle?.nodeId === params.nodeId ? pendingHandle.handleId : params.handleId

        // Prevent starting a new connection from the loop handle if it already has a connection
        if (handleId === EdgeHandleEnum.LOOP) {
          const hasExistingLoopConnection = edges.some(
            (edge) =>
              edge.source === params.nodeId &&
              edge.sourceHandle === EdgeHandleEnum.LOOP &&
              edge.type !== 'buttonEdge' &&
              !edge.id.startsWith('button-')
          )
          if (hasExistingLoopConnection) {
            // Don't set connection state - this prevents the drag from starting
            return
          }
        }

        connectionStateRef.current.sourceNodeId = params.nodeId
        connectionStateRef.current.sourceHandleId = handleId
        connectionStateRef.current.successful = false
      }
    },
    [edges]
  )

  const onConnectEnd = useCallback(
    (event: MouseEvent | TouchEvent) => {
      const { sourceNodeId, sourceHandleId, successful: wasSuccessful } = connectionStateRef.current
      connectionStateRef.current.sourceNodeId = null
      connectionStateRef.current.sourceHandleId = null
      connectionStateRef.current.successful = false

      if (!sourceNodeId || wasSuccessful) return

      const target = event.target as HTMLElement
      const isCanvas = target.classList.contains('react-flow__pane')

      if (isCanvas) {
        const mouseEvent = event as MouseEvent
        const clientX = mouseEvent.clientX
        const clientY = mouseEvent.clientY

        const flowPosition = screenToFlowPosition({ x: clientX, y: clientY })

        setPendingEdge({
          sourceNodeId,
          sourceHandle: sourceHandleId ?? undefined,
          x: flowPosition.x,
          y: flowPosition.y,
        })

        onAddNodeFromEdge?.(sourceNodeId, undefined, undefined, sourceHandleId ?? undefined, flowPosition)
      }
    },
    [onAddNodeFromEdge, screenToFlowPosition, setPendingEdge]
  )

  return {
    onConnect,
    onConnectStart,
    onConnectEnd,
  }
}
