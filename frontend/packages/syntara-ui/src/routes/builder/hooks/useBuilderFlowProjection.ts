import { useMemo } from 'react'

import { projectBuilderFlowGraph } from '../projectBuilderFlowGraph'

type BuilderFlowProjectionOptions = Parameters<typeof projectBuilderFlowGraph>[0]

export function useBuilderFlowProjection(options: BuilderFlowProjectionOptions) {
  const {
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
  } = options

  return useMemo(
    () =>
      projectBuilderFlowGraph({
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
      }),
    [
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
    ]
  )
}
