import type { Dispatch, SetStateAction } from 'react'

import { FlowNodeType } from '../../../constants'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { EdgeType } from '../utils/workflowToGraph'

/**
 * Merges initialNodes with prevNodes, preserving position and measured dimensions
 * for existing nodes and keeping nodes not in initialNodes (e.g. placeholders).
 */
export function mergeNodesPreservingPositions(prevNodes: NodeType[], initialNodes: NodeType[]): NodeType[] {
  const prevNodeMap = new Map(prevNodes.map((node) => [node.id, node]))
  const initialNodeIds = new Set(initialNodes.map((node) => node.id))
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

export type NodeUpdateTracking = {
  previousNodeIds: Set<string>
  previousInitialNodes: NodeType[]
  previousInitialEdges: EdgeType[]
}

type NodeUpdatePlanOptions = {
  initialNodes: NodeType[]
  initialEdges: EdgeType[]
  previousNodeIds: Set<string>
  previousInitialNodes: NodeType[]
  previousInitialEdges: EdgeType[]
  newlyAddedNodeIds: Set<string>
  isInitialized: boolean
}

export type NodeUpdatePlan =
  | { type: 'none' }
  | { type: 'already-tracked-addition'; currentNodeIds: Set<string> }
  | {
      type: 'add-nodes'
      currentNodeIds: Set<string>
      newNodeIds: string[]
      hasDeletedNodes: boolean
      edgesDataChanged: boolean
    }
  | { type: 'delete-nodes'; currentNodeIds: Set<string> }
  | { type: 'update-node-data' }
  | { type: 'initialize-nodes'; currentNodeIds: Set<string> }
  | { type: 'update-snapshots-only' }

/** Describes how the owning BuilderFlow should reconcile its controlled graph state. */
export function getNodeUpdatePlan({
  initialNodes,
  initialEdges,
  previousNodeIds,
  previousInitialNodes,
  previousInitialEdges,
  newlyAddedNodeIds,
  isInitialized,
}: NodeUpdatePlanOptions): NodeUpdatePlan {
  const nodesDataChanged =
    initialNodes.length !== previousInitialNodes.length ||
    initialNodes.some((node, index) => {
      const previousNode = previousInitialNodes[index]
      return (
        node.id !== previousNode?.id ||
        node.type !== previousNode?.type ||
        JSON.stringify(node.data) !== JSON.stringify(previousNode?.data)
      )
    })

  const edgesDataChanged =
    initialEdges.length !== previousInitialEdges.length ||
    initialEdges.some((edge, index) => {
      const previousEdge = previousInitialEdges[index]
      return (
        edge.id !== previousEdge?.id || edge.source !== previousEdge?.source || edge.target !== previousEdge?.target
      )
    })

  if (!nodesDataChanged && !edgesDataChanged) return { type: 'none' }

  const currentNodeIds = new Set(initialNodes.map((node) => node.id))
  const newNodeIds = Array.from(currentNodeIds).filter((id) => !previousNodeIds.has(id))
  const hasNewNodes = newNodeIds.length > 0
  const hasDeletedNodes = Array.from(previousNodeIds).some((id) => !currentNodeIds.has(id))

  if (hasNewNodes && isInitialized) {
    if (newNodeIds.every((id) => newlyAddedNodeIds.has(id))) {
      return { type: 'already-tracked-addition', currentNodeIds }
    }

    return { type: 'add-nodes', currentNodeIds, newNodeIds, hasDeletedNodes, edgesDataChanged }
  }

  if (isInitialized && hasDeletedNodes) return { type: 'delete-nodes', currentNodeIds }
  if (isInitialized && nodesDataChanged) return { type: 'update-node-data' }
  if (!isInitialized) return { type: 'initialize-nodes', currentNodeIds }
  return { type: 'update-snapshots-only' }
}

export function keepCurrentNodesAndPlaceholders(nodes: NodeType[], initialNodes: NodeType[]): NodeType[] {
  const initialNodeIds = new Set(initialNodes.map((node) => node.id))
  return nodes.filter((node) => initialNodeIds.has(node.id) || (node.type as string) === FlowNodeType.PLACEHOLDER)
}

type ReconcileBuilderFlowNodesOptions = {
  initialNodes: NodeType[]
  initialEdges: EdgeType[]
  isInitialized: boolean
  tracking: NodeUpdateTracking
  newlyAddedNodeIds: Set<string>
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
}

/** Applies an update plan to the React Flow state owned by BuilderFlow. */
export function reconcileBuilderFlowNodes({
  initialNodes,
  initialEdges,
  isInitialized,
  tracking,
  newlyAddedNodeIds,
  setNodes,
  setEdges,
}: ReconcileBuilderFlowNodesOptions): void {
  const plan = getNodeUpdatePlan({
    initialNodes,
    initialEdges,
    previousNodeIds: tracking.previousNodeIds,
    previousInitialNodes: tracking.previousInitialNodes,
    previousInitialEdges: tracking.previousInitialEdges,
    newlyAddedNodeIds,
    isInitialized,
  })

  if (plan.type === 'none') return

  if (plan.type === 'already-tracked-addition') {
    tracking.previousNodeIds = plan.currentNodeIds
    return
  }

  if (plan.type === 'add-nodes') {
    plan.newNodeIds.forEach((id) => newlyAddedNodeIds.add(id))

    setNodes((previousNodes) => {
      const merged = mergeNodesPreservingPositions(previousNodes, initialNodes)
      return plan.hasDeletedNodes ? keepCurrentNodesAndPlaceholders(merged, initialNodes) : merged
    })

    if (plan.edgesDataChanged) {
      setEdges((previousEdges) => {
        const previousEdgeIds = new Set(previousEdges.map((edge) => edge.id))
        const newEdges = initialEdges.filter((edge) => !previousEdgeIds.has(edge.id))
        return [...previousEdges, ...newEdges]
      })
    }

    tracking.previousNodeIds = plan.currentNodeIds
  } else if (plan.type === 'delete-nodes') {
    setNodes((previousNodes) =>
      keepCurrentNodesAndPlaceholders(mergeNodesPreservingPositions(previousNodes, initialNodes), initialNodes)
    )
    tracking.previousNodeIds = plan.currentNodeIds
  } else if (plan.type === 'update-node-data') {
    setNodes((previousNodes) => mergeNodesPreservingPositions(previousNodes, initialNodes))
  } else if (plan.type === 'initialize-nodes') {
    setNodes(initialNodes)
    tracking.previousNodeIds = plan.currentNodeIds
  }

  tracking.previousInitialNodes = initialNodes
  tracking.previousInitialEdges = initialEdges
}
