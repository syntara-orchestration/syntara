import type { ReactFlowInstance } from '@xyflow/react'
import type { Dispatch, RefObject, SetStateAction } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { OnAddNodeFromEdge } from '../types'
import type { EdgeConnection } from '../types/edge'
import type { EdgeType } from '../utils/workflowToGraph'

import { useNodeDeletion } from './useNodeDeletion'
import { useNodePositioning } from './useNodePositioning'

export type BuilderFlowGraphState = {
  nodes: NodeType[]
  edges: EdgeType[]
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  newlyAddedNodeIdsRef: RefObject<Set<string>>
  isDeletingRef: RefObject<boolean>
}

export type BuilderFlowWorkflowContext = {
  storedEdges: EdgeConnection[]
  isInitialized: boolean
}

export type BuilderFlowPanelState = {
  newNodeDesiredPosition?: { x: number; y: number } | null
  onClearDesiredPosition?: () => void
}

export type BuilderFlowCallbacks = {
  onAddNodeFromEdge?: OnAddNodeFromEdge
  onNodesDeleted?: (deletedNodeIds: string[]) => void
}

export type BuilderFlowCanvasRefs = {
  containerRef: RefObject<HTMLDivElement | null>
  reactFlowInstance: Pick<ReactFlowInstance, 'getViewport' | 'updateNode'>
}

type UseBuilderFlowSideEffectsParams = {
  graph: BuilderFlowGraphState
  workflow: BuilderFlowWorkflowContext
  panel: BuilderFlowPanelState
  callbacks: BuilderFlowCallbacks
  refs: BuilderFlowCanvasRefs
}

export function useBuilderFlowSideEffects({
  graph,
  workflow,
  panel,
  callbacks,
  refs,
}: UseBuilderFlowSideEffectsParams) {
  const { nodes, edges, setNodes, setEdges, newlyAddedNodeIdsRef, isDeletingRef } = graph
  const { storedEdges, isInitialized } = workflow
  const { newNodeDesiredPosition, onClearDesiredPosition } = panel
  const { onAddNodeFromEdge, onNodesDeleted } = callbacks
  const { containerRef, reactFlowInstance } = refs

  const { showError } = useAlerts()
  const { updateNodePositions } = useWorkflowStoreActions()
  const { getViewport, updateNode } = reactFlowInstance

  const { onNodesDelete } = useNodeDeletion({
    nodes,
    edges: storedEdges,
    setNodes,
    setEdges,
    isDeletingRef,
    onAddNodeFromEdge,
    onNodesDeleted,
    onError: (message) => showError({ title: message }),
  })

  useNodePositioning({
    nodes,
    edges,
    isInitialized,
    newlyAddedNodeIdsRef,
    containerRef,
    setNodes,
    getViewport,
    updateNode,
    updateNodePositions,
    desiredPosition: newNodeDesiredPosition ?? null,
    onClearDesiredPosition,
  })

  return { onNodesDelete }
}
