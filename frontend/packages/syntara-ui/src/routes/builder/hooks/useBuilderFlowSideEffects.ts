import type { ReactFlowInstance } from '@xyflow/react'
import type { Dispatch, RefObject, SetStateAction } from 'react'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { WorkflowDefinition } from '../../../stores/workflowStoreTypes'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../../workflows/execution/types'
import type { ValidationError } from '../builderReducer'
import type { PendingEdge } from '../types'
import type { EdgeConnection } from '../types/edge'
import type { EdgeType } from '../utils/workflowToGraph'

import { useButtonEdgeMaintenance } from './useButtonEdgeMaintenance'
import { useEdgeActiveState } from './useEdgeActiveState'
import { useEdgeExecutionStatus } from './useEdgeExecutionStatus'
import { useEdgeSynchronization } from './useEdgeSynchronization'
import { useExecutionStateEnrichment } from './useExecutionStateEnrichment'
import { useLoopBackNodeTypes } from './useLoopBackNodeTypes'
import { useLoopGroupPositionSync } from './useLoopGroupPositionSync'
import { useNodeDeletion } from './useNodeDeletion'
import { useNodePositioning } from './useNodePositioning'
import { useNodeUpdates } from './useNodeUpdates'
import { usePendingEdgeManagement } from './usePendingEdgeManagement'
import { useValidationEnrichment } from './useValidationEnrichment'

export type BuilderFlowGraphState = {
  nodes: NodeType[]
  edges: EdgeType[]
  initialNodes: NodeType[]
  initialEdges: EdgeType[]
  setNodes: Dispatch<SetStateAction<NodeType[]>>
  setEdges: Dispatch<SetStateAction<EdgeType[]>>
  isDeletingRef: RefObject<boolean>
}

export type BuilderFlowWorkflowContext = {
  workflowVersion: number
  currentWorkflow: WorkflowDefinition | null
  storedEdges: EdgeConnection[]
  isInitialized: boolean
  isReadOnly: boolean
}

export type BuilderFlowExecutionState = {
  isActiveExecution: boolean
  isExecutionView: boolean
  effectiveExecutionStatus: string | null
  activityStates: Map<string, ActivityState>
  preResolvedNodes: Set<string>
  copiedRunActivityIds?: ReadonlySet<string> | null
  validationErrors?: ValidationError[]
  buttonEdgeExecutionStatus: string | null
}

export type BuilderFlowPanelState = {
  pendingEdge: PendingEdge | null
  activeEdgeButtonNodeId?: string | null
  activeEdgeButtonHandle?: string | null
  activeEdgeId?: string | null
  newNodeDesiredPosition?: { x: number; y: number } | null
  onClearDesiredPosition?: () => void
}

export type BuilderFlowCallbacks = {
  onAddNodeFromEdge?: (
    sourceNodeId: string,
    targetNodeId?: string,
    edgeId?: string,
    sourceHandle?: string,
    desiredPosition?: { x: number; y: number }
  ) => void
  onNodesDeleted?: (deletedNodeIds: string[]) => void
}

export type BuilderFlowCanvasRefs = {
  containerRef: RefObject<HTMLDivElement | null>
  reactFlowInstance: Pick<ReactFlowInstance, 'getViewport' | 'updateNode'>
}

type UseBuilderFlowSideEffectsParams = {
  graph: BuilderFlowGraphState
  workflow: BuilderFlowWorkflowContext
  execution: BuilderFlowExecutionState
  panel: BuilderFlowPanelState
  callbacks: BuilderFlowCallbacks
  refs: BuilderFlowCanvasRefs
}

export function useBuilderFlowSideEffects({
  graph,
  workflow,
  execution,
  panel,
  callbacks,
  refs,
}: UseBuilderFlowSideEffectsParams) {
  const { nodes, edges, initialNodes, initialEdges, setNodes, setEdges, isDeletingRef } = graph
  const { workflowVersion, currentWorkflow, storedEdges, isInitialized, isReadOnly } = workflow
  const {
    isActiveExecution,
    isExecutionView,
    effectiveExecutionStatus,
    activityStates,
    preResolvedNodes,
    copiedRunActivityIds,
    validationErrors,
    buttonEdgeExecutionStatus,
  } = execution
  const {
    pendingEdge,
    activeEdgeButtonNodeId,
    activeEdgeButtonHandle,
    activeEdgeId,
    newNodeDesiredPosition,
    onClearDesiredPosition,
  } = panel
  const { onAddNodeFromEdge, onNodesDeleted } = callbacks
  const { containerRef, reactFlowInstance } = refs

  const { showError } = useAlerts()
  const { setEdges: setStoredEdges, updateNodePositions } = useWorkflowStoreActions()
  const { getViewport, updateNode } = reactFlowInstance

  const { newlyAddedNodeIdsRef } = useNodeUpdates({
    initialNodes,
    initialEdges,
    isInitialized,
    setNodes,
    setEdges,
    workflowVersion,
  })

  useEdgeSynchronization({
    edges,
    isInitialized,
    setStoredEdges,
    workflowVersion,
    isActiveExecution,
  })

  useLoopBackNodeTypes({ edges, isInitialized, setNodes })

  useLoopGroupPositionSync({
    nodes,
    edges,
    isInitialized,
    workflowVersion,
    triggers: currentWorkflow?.triggers ?? [],
    updateNodePositions,
  })

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

  useButtonEdgeMaintenance({
    nodes,
    edges,
    isInitialized,
    activeEdgeButtonNodeId: activeEdgeButtonNodeId ?? null,
    activeEdgeButtonHandle: activeEdgeButtonHandle ?? null,
    onAddNodeFromEdge,
    pendingEdge,
    setNodes,
    setEdges,
    executionStatus: buttonEdgeExecutionStatus,
    isReadOnly,
  })

  useEdgeActiveState({
    isInitialized,
    activeEdgeId: activeEdgeId ?? null,
    activeEdgeButtonNodeId: activeEdgeButtonNodeId ?? null,
    activeEdgeButtonHandle: activeEdgeButtonHandle ?? null,
    onAddNodeFromEdge,
    setEdges,
  })

  usePendingEdgeManagement({
    pendingEdge,
    isInitialized,
    setNodes,
    setEdges,
  })

  useExecutionStateEnrichment({
    effectiveExecutionStatus,
    isInitialized,
    currentWorkflow,
    activityStates,
    preResolvedNodes,
    copiedRunActivityIds,
    setNodes,
  })

  useValidationEnrichment(validationErrors, isInitialized, setNodes)

  useEdgeExecutionStatus({
    effectiveExecutionStatus,
    isInitialized,
    currentWorkflow,
    activityStates,
    storedEdges,
    setEdges,
    isExecutionDetailView: isExecutionView,
  })

  return { onNodesDelete }
}
