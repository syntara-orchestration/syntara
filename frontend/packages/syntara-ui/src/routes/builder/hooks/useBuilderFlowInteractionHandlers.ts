import type { Node, ReactFlowInstance } from '@xyflow/react'
import { useCallback, useMemo, type Dispatch } from 'react'

import { getActivityMetadata, useWorkflowStore } from '../../../stores/useWorkflowStore'
import type { NodeType } from '../../workflows/canvas/nodes/NodeType'
import type { BuilderAction } from '../builderReducer'
import { findDuplicatePosition } from '../duplicateNodePosition'
import type { NodeActionsContextValue } from '../NodeActionsContext'
import type { FlowPosition } from '../types'
import { applyEdgeConnection, calculateEdgeConnection } from '../utils/edgeConnectionHelpers'

export type UseBuilderFlowInteractionHandlersOptions = {
  reactFlowInstance: ReactFlowInstance
  dispatch: Dispatch<BuilderAction>
  duplicateActivity: (nodeId: string) => void
  edgeIdToReplace: string | null
  targetNodeId: string | null
  sourceHandle: string | null | undefined
  targetHandle: string | null | undefined
  onRunStep: (nodeId: string) => void
}

/**
 * React Flow node/edge interaction handlers for the workflow builder canvas.
 */
export function useBuilderFlowInteractionHandlers({
  reactFlowInstance,
  dispatch,
  duplicateActivity,
  edgeIdToReplace,
  targetNodeId,
  sourceHandle,
  targetHandle,
  onRunStep,
}: UseBuilderFlowInteractionHandlersOptions) {
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node<NodeType['data']>) => {
      const isGeneric = getActivityMetadata(node.data)?.__isGeneric === true
      dispatch({ type: 'NODE_CLICK', payload: { node, isGeneric } })
    },
    [dispatch]
  )

  const handleClearDesiredPosition = useCallback(
    () => dispatch({ type: 'CLEAR_NEW_NODE_DESIRED_POSITION' }),
    [dispatch]
  )

  const handleAddNodeFromEdge = useCallback(
    (sourceId: string, targetId?: string, edgeId?: string, handle?: string, desiredPosition?: FlowPosition) => {
      let edgeTargetHandle: string | undefined = undefined
      if (edgeId) {
        const edge = reactFlowInstance.getEdge(edgeId)
        edgeTargetHandle = edge?.targetHandle ?? undefined
      }
      dispatch({
        type: 'OPEN_ADD_NODE_FROM_EDGE',
        payload: { sourceId, targetId, edgeId, handle, targetHandle: edgeTargetHandle, desiredPosition },
      })
    },
    [dispatch, reactFlowInstance]
  )

  const handleConnectFromPanel = useCallback(
    (sourceId: string, targetId: string) => {
      const params = {
        sourceId,
        targetId,
        edgeIdToReplace,
        targetNodeId,
        sourceHandle: sourceHandle ?? undefined,
        targetHandle: targetHandle ?? undefined,
        onAddNode: handleAddNodeFromEdge,
      }

      const result = calculateEdgeConnection(params, reactFlowInstance)

      applyEdgeConnection(result, params, targetId, reactFlowInstance, () => {
        if (result.activityReorderTarget) {
          useWorkflowStore.getState().moveActivityBefore(targetId, result.activityReorderTarget)
        }
      })
    },
    [edgeIdToReplace, targetNodeId, sourceHandle, targetHandle, reactFlowInstance, handleAddNodeFromEdge]
  )

  const handleNodesDeleted = useCallback(
    (deletedNodeIds: string[]) => {
      dispatch({ type: 'CLEAR_SELECTED_IF_DELETED', payload: deletedNodeIds })
    },
    [dispatch]
  )

  const handleViewNodeDetails = useCallback(
    (nodeId: string) => {
      const node = reactFlowInstance.getNode(nodeId)
      if (!node) return
      const isGeneric = getActivityMetadata(node.data)?.__isGeneric === true
      dispatch({
        type: 'NODE_CLICK',
        // React Flow widens getNode().data; builder state expects Node<NodeType['data']>
        payload: { node: node, isGeneric },
      })
    },
    [dispatch, reactFlowInstance]
  )

  const handleReplaceNode = useCallback(
    (nodeId: string) => {
      dispatch({ type: 'OPEN_ADD_NODE_PANEL', payload: { sourceNodeId: null, replacementNodeId: nodeId } })
    },
    [dispatch]
  )

  const handleDuplicateNode = useCallback(
    (nodeId: string) => {
      const node = reactFlowInstance.getNode(nodeId)
      dispatch({ type: 'CLOSE_NODE_EDITOR' })
      if (node) {
        const allNodes = reactFlowInstance.getNodes()
        const { x, y } = findDuplicatePosition(node, allNodes)
        const nodeHeight = node.measured?.height ?? 60
        dispatch({
          type: 'SET_NEW_NODE_DESIRED_POSITION',
          payload: { x, y: y + nodeHeight / 2 },
        })
      }
      duplicateActivity(nodeId)
    },
    [dispatch, reactFlowInstance, duplicateActivity]
  )

  const handleToggleDisabled = useCallback((nodeId: string) => {
    const store = useWorkflowStore.getState()
    const activities = store.currentWorkflow?.workflow.activities ?? []
    const activity = activities.find((a) => a.id === nodeId)
    if (!activity) return
    const currentDisabled = activity.settings?.disabled ?? false
    store.updateActivity(nodeId, {
      settings: { ...activity.settings, disabled: !currentDisabled },
    })
  }, [])

  const nodeActionsValue = useMemo<NodeActionsContextValue>(
    () => ({
      onViewDetails: handleViewNodeDetails,
      onReplace: handleReplaceNode,
      onDuplicate: handleDuplicateNode,
      onRunStep,
      onToggleDisabled: handleToggleDisabled,
    }),
    [handleViewNodeDetails, handleReplaceNode, handleDuplicateNode, onRunStep, handleToggleDisabled]
  )

  return {
    handleNodeClick,
    handleClearDesiredPosition,
    handleAddNodeFromEdge,
    handleConnectFromPanel,
    handleNodesDeleted,
    nodeActionsValue,
  }
}
