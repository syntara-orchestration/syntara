import type { WorkflowDefinition } from '../../stores/workflowStoreTypes'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'
import type { ActivityState } from '../workflows/execution/types'

import type { ValidationError } from './builderReducer'
import { projectButtonEdgeMaintenance } from './hooks/useButtonEdgeMaintenance'
import { projectEdgeActiveState } from './hooks/useEdgeActiveState'
import { projectEdgeExecutionStatus } from './hooks/useEdgeExecutionStatus'
import { projectExecutionState } from './hooks/useExecutionStateEnrichment'
import { projectExternalNodeSelection } from './hooks/useExternalNodeSelection'
import { projectLoopBackNodeTypes } from './hooks/useLoopBackNodeTypes'
import { projectPendingEdgeGraph } from './hooks/usePendingEdgeManagement'
import { projectValidationEnrichment } from './hooks/useValidationEnrichment'
import type { OnAddNodeFromEdge, PendingEdge } from './types'
import type { EdgeConnection } from './types/edge'
import type { EdgeType } from './utils/workflowToGraph'

type ProjectBuilderFlowGraphOptions = {
  nodes: NodeType[]
  edges: EdgeType[]
  isInitialized: boolean
  selectedActivityId?: string | null
  activeEdgeId?: string | null
  activeEdgeButtonNodeId?: string | null
  activeEdgeButtonHandle?: string | null
  onAddNodeFromEdge?: OnAddNodeFromEdge
  pendingEdge: PendingEdge | null
  buttonEdgeExecutionStatus: string | null
  isReadOnly: boolean
  effectiveExecutionStatus: string | null
  isExecutionDetailView: boolean
  currentWorkflow: WorkflowDefinition | null
  activityStates: Map<string, ActivityState>
  storedEdges: EdgeConnection[]
  triggers: Array<{ id: string }>
  preResolvedNodes: Set<string>
  copiedRunActivityIds?: ReadonlySet<string> | null
  validationErrors?: ValidationError[]
}

/** Builds the canvas graph from controlled state and view-only projections. */
export function projectBuilderFlowGraph({
  nodes,
  edges,
  isInitialized,
  selectedActivityId,
  activeEdgeId,
  activeEdgeButtonNodeId,
  activeEdgeButtonHandle,
  onAddNodeFromEdge,
  pendingEdge,
  buttonEdgeExecutionStatus,
  isReadOnly,
  effectiveExecutionStatus,
  isExecutionDetailView,
  currentWorkflow,
  activityStates,
  storedEdges,
  triggers,
  preResolvedNodes,
  copiedRunActivityIds,
  validationErrors,
}: ProjectBuilderFlowGraphOptions): { nodes: NodeType[]; edges: EdgeType[] } {
  const buttonEdgeGraph = projectButtonEdgeMaintenance({
    nodes,
    edges,
    isInitialized,
    activeEdgeButtonNodeId: activeEdgeButtonNodeId ?? null,
    activeEdgeButtonHandle: activeEdgeButtonHandle ?? null,
    onAddNodeFromEdge,
    pendingEdge,
    executionStatus: buttonEdgeExecutionStatus,
    isReadOnly,
  })
  const pendingEdgeGraph = projectPendingEdgeGraph(
    buttonEdgeGraph.nodes,
    buttonEdgeGraph.edges,
    isReadOnly || buttonEdgeExecutionStatus ? null : pendingEdge,
    isInitialized
  )

  const selectedNodes = projectExternalNodeSelection(pendingEdgeGraph.nodes, selectedActivityId)
  const executionNodes = projectExecutionState(selectedNodes, {
    effectiveExecutionStatus,
    currentWorkflow,
    activityStates,
    storedEdges,
    preResolvedNodes,
    copiedRunActivityIds,
  })
  const loopBackNodes = projectLoopBackNodeTypes(executionNodes, pendingEdgeGraph.edges, isInitialized)
  const validationNodes = projectValidationEnrichment(loopBackNodes, validationErrors, triggers, isInitialized)

  const activeEdges = projectEdgeActiveState(pendingEdgeGraph.edges, {
    activeEdgeId: activeEdgeId ?? null,
    activeEdgeButtonNodeId: activeEdgeButtonNodeId ?? null,
    activeEdgeButtonHandle: activeEdgeButtonHandle ?? null,
    onAddNodeFromEdge,
    isInitialized,
  })
  const executionEdges = projectEdgeExecutionStatus(activeEdges, {
    effectiveExecutionStatus,
    currentWorkflow,
    activityStates,
    storedEdges,
    isExecutionDetailView,
  })

  return { nodes: validationNodes, edges: executionEdges }
}
