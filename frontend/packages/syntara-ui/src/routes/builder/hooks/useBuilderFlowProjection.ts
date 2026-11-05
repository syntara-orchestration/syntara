import { useMemo } from 'react'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import { projectBuilderFlowGraph } from '../projectBuilderFlowGraph'
import { isPlaceholderNode } from '../utils/filterHelpers'

type BuilderFlowProjectionOptions = Parameters<typeof projectBuilderFlowGraph>[0]

type PlaceholderNodeSnapshot = Pick<
  NodeType,
  'id' | 'type' | 'position' | 'data' | 'draggable' | 'selectable' | 'hidden' | 'style' | 'className'
>

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

  const projectedGraph = useMemo(
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

  // Preserve placeholder identity across unrelated graph updates so React Flow keeps its handle measurements.
  const placeholderNodeSignature = JSON.stringify(
    projectedGraph.nodes
      .filter(isPlaceholderNode)
      .map(
        ({ id, type, position, data, draggable, selectable, hidden, style, className }): PlaceholderNodeSnapshot => ({
          id,
          type,
          position,
          data,
          draggable,
          selectable,
          hidden,
          style,
          className,
        })
      )
      .sort((a, b) => a.id.localeCompare(b.id))
  )
  const stablePlaceholderNodesById = useMemo(
    () =>
      new Map(
        (JSON.parse(placeholderNodeSignature) as PlaceholderNodeSnapshot[]).map((node) => [node.id, node as NodeType])
      ),
    [placeholderNodeSignature]
  )

  const graphWithStablePlaceholderNodes = useMemo(() => {
    let hasReusedNode = false
    const nodes = projectedGraph.nodes.map((node) => {
      if (!isPlaceholderNode(node)) return node

      const stableNode = stablePlaceholderNodesById.get(node.id)
      if (stableNode) {
        hasReusedNode ||= stableNode !== node
        return stableNode
      }
      return node
    })

    return hasReusedNode ? { ...projectedGraph, nodes } : projectedGraph
  }, [projectedGraph, stablePlaceholderNodesById])

  return graphWithStablePlaceholderNodes
}
