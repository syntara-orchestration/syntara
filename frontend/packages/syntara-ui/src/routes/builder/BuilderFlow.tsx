import { useReactFlow } from '@xyflow/react'
import { useEffect, useRef } from 'react'

import {
  useWorkflowStore,
  selectCurrentWorkflow,
  selectWorkflowVersion,
  selectPositionUndoVersion,
  selectEdges,
  selectTriggers,
  selectActivities,
  useWorkflowStoreActions,
} from '../../stores/useWorkflowStore'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import { ActiveExecutionContext } from './ActiveExecutionContext'
import { BuilderFlowCanvas } from './BuilderFlowCanvas'
import { synchronizeBuilderFlowEdges, type EdgeSynchronizationState } from './hooks/edgeSynchronization'
import { reconcileBuilderFlowNodes, type NodeUpdateTracking } from './hooks/nodeUpdates'
import { useBuilderFlowExecutionContext } from './hooks/useBuilderFlowExecutionContext'
import { useBuilderFlowGraph } from './hooks/useBuilderFlowGraph'
import { useBuilderFlowProjection } from './hooks/useBuilderFlowProjection'
import { useBuilderFlowSideEffects } from './hooks/useBuilderFlowSideEffects'
import { useCanvasInteractions } from './hooks/useCanvasInteractions'
import { useConnectionHandlers } from './hooks/useConnectionHandlers'
import { restoreNodePositions, usePositionEventHandlers } from './hooks/usePositionEventHandlers'
import { useWorkflowGraphInit } from './hooks/useWorkflowGraphInit'
import { useWorkflowInitialization } from './hooks/useWorkflowInitialization'
import type { BuilderFlowProps } from './types'

function clearBuilderFlowUndoHistory() {
  const temporal = useWorkflowStore.temporal.getState()
  if (useWorkflowStore.getState()._preserveHistoryOnLayout) {
    useWorkflowStore.setState({ _preserveHistoryOnLayout: false })
  } else {
    temporal.pause()
    temporal.clear()
  }
  setTimeout(() => temporal.resume(), 200)
}

export function BuilderFlow(props: BuilderFlowProps) {
  const { workflowId, canEdit = true, readOnly: readOnlyProp } = props
  const { panelOpen, activeEdgeButtonNodeId, activeEdgeButtonHandle, activeEdgeId } = props
  const { newNodeDesiredPosition, onClearDesiredPosition } = props
  const { executionStatus, copiedRunActivityIds, onNodeClick, onAddNodeFromEdge, onNodesDeleted } = props
  const { disableDeleteKey, disableSpacePanning, selectedActivityId, validationErrors } = props

  const workflowVersion = useWorkflowStore(selectWorkflowVersion)
  const positionUndoVersion = useWorkflowStore(selectPositionUndoVersion)
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
    workflowVersion,
  })

  const { nodes, edges, setNodes, setEdges, isDeletingRef } = useWorkflowGraphInit({
    workflowId,
    workflowVersion,
    initialNodes,
    initialEdges,
  })

  const { setEdges: setStoredEdges } = useWorkflowStoreActions()
  const newlyAddedNodeIdsRef = useRef(new Set<string>())
  const nodeUpdateTrackingRef = useRef<NodeUpdateTracking>({
    previousNodeIds: new Set(initialNodes.map((node) => node.id)),
    previousInitialNodes: initialNodes,
    previousInitialEdges: initialEdges,
  })
  const nodeUpdateWorkflowVersionRef = useRef(workflowVersion)
  const edgeSyncTrackingRef = useRef<EdgeSynchronizationState>({
    lastEdgesSignature: '',
    isSyncing: false,
    isFirstSync: true,
  })
  const positionUndoVersionRef = useRef(positionUndoVersion)

  useEffect(() => {
    if (positionUndoVersion === positionUndoVersionRef.current) return
    positionUndoVersionRef.current = positionUndoVersion
    const positions = useWorkflowStore.getState().nodePositions
    if (Object.keys(positions).length === 0) return
    setNodes((previousNodes) => restoreNodePositions(previousNodes, positions, currentWorkflow?.triggers ?? []))
  }, [positionUndoVersion, currentWorkflow?.triggers, setNodes])

  const { onNodeDragStart, onNodeDrag, onNodeDragStop, onLayout } = usePositionEventHandlers(
    nodes,
    edges,
    setNodes,
    setEdges
  )

  const { isInitialized } = useWorkflowInitialization({
    nodes,
    workflowVersion,
    onLayout,
    onAfterInitialLayout: clearBuilderFlowUndoHistory,
  })

  const { fitView, screenToFlowPosition } = reactFlowInstance
  const { onNodesChange, onEdgesChange, pendingEdge, setPendingEdge, isValidConnection } = useCanvasInteractions({
    isReadOnly,
    edges,
    nodes,
    panelOpen,
    fitView,
    isInitialized,
    setNodes,
    setEdges,
  })

  const projectedGraph = useBuilderFlowProjection({
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
    isExecutionDetailView: isExecutionView,
    currentWorkflow,
    activityStates,
    storedEdges,
    triggers: triggers ?? [],
    preResolvedNodes,
    copiedRunActivityIds,
    validationErrors,
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

  useEffect(() => {
    if (nodeUpdateWorkflowVersionRef.current !== workflowVersion) {
      nodeUpdateWorkflowVersionRef.current = workflowVersion
      nodeUpdateTrackingRef.current = {
        previousNodeIds: new Set(initialNodes.map((node) => node.id)),
        previousInitialNodes: initialNodes,
        previousInitialEdges: initialEdges,
      }
      newlyAddedNodeIdsRef.current = new Set()
      return
    }

    reconcileBuilderFlowNodes({
      initialNodes,
      initialEdges,
      tracking: nodeUpdateTrackingRef.current,
      newlyAddedNodeIds: newlyAddedNodeIdsRef.current,
      isInitialized,
      setNodes,
      setEdges,
    })
  }, [initialNodes, initialEdges, isInitialized, setNodes, setEdges, workflowVersion])

  useEffect(() => {
    const tracking = edgeSyncTrackingRef.current
    tracking.isFirstSync = true
    tracking.lastEdgesSignature = ''
  }, [workflowVersion])

  useEffect(() => {
    synchronizeBuilderFlowEdges({
      edges,
      isInitialized,
      isActiveExecution,
      state: edgeSyncTrackingRef.current,
      setStoredEdges,
    })
  }, [edges, isInitialized, setStoredEdges, isActiveExecution])

  const { onNodesDelete } = useBuilderFlowSideEffects({
    graph: {
      nodes,
      edges,
      setNodes,
      setEdges,
      newlyAddedNodeIdsRef,
      isDeletingRef,
    },
    workflow: {
      storedEdges,
      isInitialized,
    },
    panel: {
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
        nodes={projectedGraph.nodes}
        edges={projectedGraph.edges}
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
