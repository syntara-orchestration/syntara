import { useReactFlow } from '@xyflow/react'
import { useCallback, useRef } from 'react'

import {
  useWorkflowStore,
  selectCurrentWorkflow,
  selectWorkflowVersion,
  selectEdges,
  selectTriggers,
  selectActivities,
} from '../../stores/useWorkflowStore'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import { ActiveExecutionContext } from './ActiveExecutionContext'
import { BuilderFlowCanvas } from './BuilderFlowCanvas'
import { useBuilderFlowExecutionContext } from './hooks/useBuilderFlowExecutionContext'
import { useBuilderFlowGraph } from './hooks/useBuilderFlowGraph'
import { useBuilderFlowSideEffects } from './hooks/useBuilderFlowSideEffects'
import { useCanvasInteractions } from './hooks/useCanvasInteractions'
import { useConnectionHandlers } from './hooks/useConnectionHandlers'
import { usePositionEventHandlers } from './hooks/usePositionEventHandlers'
import { useWorkflowGraphInit } from './hooks/useWorkflowGraphInit'
import { useWorkflowInitialization } from './hooks/useWorkflowInitialization'
import type { BuilderFlowProps } from './types'

export function BuilderFlow(props: BuilderFlowProps) {
  const {
    workflowId,
    canEdit = true,
    panelOpen,
    activeEdgeButtonNodeId,
    activeEdgeButtonHandle,
    activeEdgeId,
    executionStatus,
    copiedRunActivityIds,
    onNodeClick,
    onAddNodeFromEdge,
    onNodesDeleted,
    disableDeleteKey,
    disableSpacePanning,
    readOnly: readOnlyProp,
    newNodeDesiredPosition,
    onClearDesiredPosition,
    selectedActivityId,
    validationErrors,
  } = props

  const workflowVersion = useWorkflowStore(selectWorkflowVersion)
  const currentWorkflow = useWorkflowStore(selectCurrentWorkflow)
  const storedEdges = useWorkflowStore(selectEdges)
  const triggers = useWorkflowStore(selectTriggers)
  const activities = useWorkflowStore(selectActivities)
  const activityStates = useExecutionStore((state) => state.activityStates)
  const reactFlowInstance = useReactFlow()
  const containerRef = useRef<HTMLDivElement>(null)

  const {
    isExecutionView,
    effectiveExecutionStatus,
    isActiveExecution,
    isReadOnly,
    buttonEdgeExecutionStatus,
    preResolvedNodes,
  } = useBuilderFlowExecutionContext({ executionStatus, readOnlyProp, canEdit })

  const { nodes: initialNodes, edges: initialEdges } = useBuilderFlowGraph({
    currentWorkflow,
    triggers,
    activities,
    storedEdges,
    executionStatus: effectiveExecutionStatus,
    activityStates,
    onAddNodeFromEdge,
    workflowVersion,
    preResolvedNodes,
    skipInferenceActivityIds: copiedRunActivityIds,
  })

  const { nodes, edges, setNodes, setEdges, isDeletingRef } = useWorkflowGraphInit({
    workflowId,
    workflowVersion,
    initialNodes,
    initialEdges,
  })

  const { onNodeDragStart, onNodeDrag, onNodeDragStop, onLayout } = usePositionEventHandlers(
    nodes,
    edges,
    setNodes,
    setEdges
  )

  const clearUndoHistory = useCallback(() => {
    const temporal = useWorkflowStore.temporal.getState()
    if (useWorkflowStore.getState()._preserveHistoryOnLayout) {
      useWorkflowStore.setState({ _preserveHistoryOnLayout: false })
    } else {
      temporal.pause()
      temporal.clear()
    }
    setTimeout(() => temporal.resume(), 200)
  }, [])
  const { isInitialized } = useWorkflowInitialization({
    nodes,
    workflowVersion,
    onLayout,
    onAfterInitialLayout: clearUndoHistory,
  })

  const { fitView, screenToFlowPosition } = reactFlowInstance
  const { onNodesChange, onEdgesChange, pendingEdge, setPendingEdge, isValidConnection } = useCanvasInteractions({
    isReadOnly,
    edges,
    nodes,
    panelOpen,
    fitView,
    isInitialized,
    selectedActivityId,
    setNodes,
    setEdges,
  })

  const { onConnect, onConnectStart, onConnectEnd } = useConnectionHandlers({
    nodes,
    edges,
    onAddNodeFromEdge,
    setNodes,
    setEdges,
    setPendingEdge,
    screenToFlowPosition,
  })

  const { onNodesDelete } = useBuilderFlowSideEffects({
    graph: {
      nodes,
      edges,
      initialNodes,
      initialEdges,
      setNodes,
      setEdges,
      isDeletingRef,
    },
    workflow: {
      workflowVersion,
      currentWorkflow,
      storedEdges,
      isInitialized,
      isReadOnly,
    },
    execution: {
      isActiveExecution,
      isExecutionView,
      effectiveExecutionStatus,
      activityStates,
      preResolvedNodes,
      copiedRunActivityIds,
      validationErrors,
      buttonEdgeExecutionStatus,
    },
    panel: {
      pendingEdge,
      activeEdgeButtonNodeId,
      activeEdgeButtonHandle,
      activeEdgeId,
      newNodeDesiredPosition,
      onClearDesiredPosition,
    },
    callbacks: {
      onAddNodeFromEdge,
      onNodesDeleted,
    },
    refs: {
      containerRef,
      reactFlowInstance,
    },
  })

  const resolvedOnNodeClick = !canEdit && !isExecutionView ? undefined : onNodeClick

  return (
    <ActiveExecutionContext.Provider value={isActiveExecution}>
      <BuilderFlowCanvas
        containerRef={containerRef}
        readOnlyProp={readOnlyProp}
        effectiveExecutionStatus={effectiveExecutionStatus}
        isReadOnly={isReadOnly}
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onNodeDragStart={isReadOnly ? undefined : onNodeDragStart}
        onNodeDrag={isReadOnly ? undefined : onNodeDrag}
        onNodeDragStop={isReadOnly ? undefined : onNodeDragStop}
        onEdgesChange={onEdgesChange}
        onNodesDelete={isReadOnly ? undefined : onNodesDelete}
        onNodeClick={resolvedOnNodeClick}
        onConnect={isReadOnly ? undefined : onConnect}
        onConnectStart={isReadOnly ? undefined : onConnectStart}
        onConnectEnd={isReadOnly ? undefined : onConnectEnd}
        isValidConnection={isValidConnection}
        disableDeleteKey={disableDeleteKey}
        disableSpacePanning={disableSpacePanning}
        onLayout={onLayout}
      />
    </ActiveExecutionContext.Provider>
  )
}
