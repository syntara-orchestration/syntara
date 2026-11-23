import { useEffect, useRef } from 'react'

import { FlowNodeType } from '../../../constants/nodeTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

/**
 * Merges initialNodes with prevNodes, preserving position and measured dimensions
 * for existing nodes and keeping nodes not in initialNodes (e.g. placeholders).
 */
export function mergeNodesPreservingPositions(prevNodes: NodeType[], initialNodes: NodeType[]): NodeType[] {
  const prevNodeMap = new Map(prevNodes.map((n) => [n.id, n]))
  const initialNodeIds = new Set(initialNodes.map((n) => n.id))
  const updatedNodes = initialNodes.map((newNode) => {
    const existingNode = prevNodeMap.get(newNode.id)
    if (existingNode) {
      const existingData = existingNode.data as Record<string, unknown> | undefined
      const merged = { ...newNode, position: existingNode.position, measured: existingNode.measured }
      if (existingData?.__validationError === true) {
        return {
          ...merged,
          data: { ...(merged.data as Record<string, unknown>), __validationError: true },
        } as unknown as NodeType
      }
      return merged
    }
    return newNode
  })
  const preservedNodes = prevNodes.filter((node) => !initialNodeIds.has(node.id))
  return [...updatedNodes, ...preservedNodes]
}

type UseNodeUpdatesOptions = {
  initialNodes: NodeType[]
  initialEdges: EdgeType[]
  isInitialized: boolean
  setNodes: React.Dispatch<React.SetStateAction<NodeType[]>>
  setEdges: React.Dispatch<React.SetStateAction<EdgeType[]>>
  onNewNodesAdded?: (newNodeIds: string[]) => void
  /** UI-only version counter — reset tracking refs when this changes (undo/redo, new workflow). */
  workflowVersion: number
}

/**
 * Custom hook that manages node and edge updates when the workflow changes.
 *
 * Handles four different update scenarios:
 * 1. New nodes added - preserves existing positions, tracks new nodes for positioning
 * 2. Nodes deleted - updates positions while preserving measured dimensions
 * 3. Node data changed - updates data without changing positions
 * 4. Initial load - sets initial nodes and edges
 */
export function useNodeUpdates({
  initialNodes,
  initialEdges,
  isInitialized,
  setNodes,
  setEdges,
  onNewNodesAdded,
  workflowVersion,
}: UseNodeUpdatesOptions) {
  const previousNodeIdsRef = useRef<Set<string>>(new Set())
  const previousInitialNodesRef = useRef<NodeType[]>(initialNodes)
  const previousInitialEdgesRef = useRef<EdgeType[]>(initialEdges)
  const newlyAddedNodeIdsRef = useRef<Set<string>>(new Set())

  // Reset tracking refs when workflowVersion changes (undo/redo, new workflow load).
  // This prevents useNodeUpdates from mis-detecting "deleted" or "new" nodes based
  // on stale refs from before the version change.
  useEffect(() => {
    previousNodeIdsRef.current = new Set(initialNodes.map((n) => n.id))
    previousInitialNodesRef.current = initialNodes
    previousInitialEdgesRef.current = initialEdges
    newlyAddedNodeIdsRef.current = new Set()
    // Only reset on version change, not when initialNodes changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowVersion])

  // Update nodes when workflow changes
  useEffect(() => {
    // Check if initialNodes/initialEdges actually changed by comparing with previous values
    // Use efficient comparison for structure, JSON.stringify only for data content
    const nodesDataChanged =
      initialNodes.length !== previousInitialNodesRef.current.length ||
      initialNodes.some((node, i) => {
        const prevNode = previousInitialNodesRef.current[i]
        return (
          node.id !== prevNode?.id ||
          node.type !== prevNode?.type ||
          JSON.stringify(node.data) !== JSON.stringify(prevNode?.data)
        )
      })

    const edgesDataChanged =
      initialEdges.length !== previousInitialEdgesRef.current.length ||
      initialEdges.some((edge, i) => {
        const prevEdge = previousInitialEdgesRef.current[i]
        return edge.id !== prevEdge?.id || edge.source !== prevEdge?.source || edge.target !== prevEdge?.target
      })

    // If nothing changed, skip the entire update.
    // This must apply regardless of isInitialized — when undo/redo triggers
    // an isInitialized true→false→true cycle, firing the !isInitialized branch
    // would overwrite correctly-positioned nodes with (0,0) defaults.
    if (!nodesDataChanged && !edgesDataChanged) {
      return
    }

    const currentNodeIds = new Set(initialNodes.map((n) => n.id))
    const previousNodeIds = previousNodeIdsRef.current

    // Check if there are new nodes
    const hasNewNodes = Array.from(currentNodeIds).some((id) => !previousNodeIds.has(id))

    // Check if node data actually changed (not just object references)
    const hasDeletedNodes = Array.from(previousNodeIds).some((id) => !currentNodeIds.has(id))

    if (hasNewNodes && isInitialized) {
      // Track which nodes are newly added (need positioning after measurement)
      const newNodeIds = Array.from(currentNodeIds).filter((id) => !previousNodeIds.has(id))

      // CRITICAL: If these nodes are already in the tracking set, it means a previous effect run
      // in this render cycle is already handling them. Skip to avoid duplicate processing.
      const alreadyTracked = newNodeIds.every((id) => newlyAddedNodeIdsRef.current.has(id))
      if (alreadyTracked) {
        previousNodeIdsRef.current = currentNodeIds
        return
      }

      newNodeIds.forEach((id) => newlyAddedNodeIdsRef.current.add(id))

      // Notify parent of new nodes
      onNewNodesAdded?.(newNodeIds)

      // Merge new nodes with existing positioned nodes, filtering stale nodes when deletions also occurred
      setNodes((prevNodes) => {
        const merged = mergeNodesPreservingPositions(prevNodes, initialNodes)
        if (hasDeletedNodes) {
          const validNodeIds = new Set(initialNodes.map((n) => n.id))
          return merged.filter(
            (node) => validNodeIds.has(node.id) || (node.type as string) === FlowNodeType.PLACEHOLDER
          )
        }
        return merged
      })

      // SPECIAL CASE: When new edges are added (e.g., loop node creation with edges)
      // Merge new edges while preserving existing ones
      if (edgesDataChanged) {
        setEdges((prevEdges) => {
          const prevEdgeIds = new Set(prevEdges.map((e) => e.id))
          const newEdges = initialEdges.filter((e) => !prevEdgeIds.has(e.id))
          // Add new edges that don't exist yet, preserve all existing edges
          return [...prevEdges, ...newEdges]
        })
      }

      // Update the ref with current node IDs
      previousNodeIdsRef.current = currentNodeIds
    } else if (isInitialized && hasDeletedNodes) {
      // Only handle deletions (new nodes handled above)
      setNodes((prevNodes) => {
        const merged = mergeNodesPreservingPositions(prevNodes, initialNodes)
        const initialNodeIds = new Set(initialNodes.map((n) => n.id))
        return merged.filter(
          (node) => initialNodeIds.has(node.id) || (node.type as string) === FlowNodeType.PLACEHOLDER
        )
      })

      // DO NOT merge initialEdges after initialization
      // Edge deletions are handled by onNodesDelete in BuilderFlow
      // Undo/redo uses workflowVersion bump which triggers full re-initialization
      previousNodeIdsRef.current = currentNodeIds
    } else if (isInitialized && nodesDataChanged) {
      // Handle data changes to existing nodes (no additions or deletions)
      setNodes((prevNodes) => mergeNodesPreservingPositions(prevNodes, initialNodes))
      // DO NOT reset edges when data changes
      // After initialization, React Flow edges are managed by user interactions (onConnect, onEdgesChange)
      // and synced to Zustand by useEdgeSynchronization
      // Resetting from initialEdges causes race conditions
    } else if (!isInitialized) {
      // Initial load - use positions from initialNodes and run layout
      setNodes(initialNodes)
      // DO NOT setEdges here - initialization is handled by BuilderFlow's controlled state
      // Setting edges here conflicts with the controlled state initialization and causes race conditions
      previousNodeIdsRef.current = currentNodeIds
    }

    // Update refs to track current state
    previousInitialNodesRef.current = initialNodes
    previousInitialEdgesRef.current = initialEdges
    // If isInitialized && !hasNewNodes && !hasDeletedNodes, skip update to prevent infinite loop
  }, [initialNodes, initialEdges, setNodes, setEdges, isInitialized, onNewNodesAdded])

  return {
    previousNodeIdsRef,
    newlyAddedNodeIdsRef,
  }
}
