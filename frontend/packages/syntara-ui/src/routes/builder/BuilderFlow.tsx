// TODO: Refactor into smaller hooks to reduce file size
// Suggested hooks: useWorkflowGraphInit, useExecutionStateEnrichment, useCanvasInteractions

import { Spinner } from '@patternfly/react-core'
import {
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ReactFlow,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from '@xyflow/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useAlerts } from '../../providers/alerts'
import {
  useWorkflowStore,
  useWorkflowStoreActions,
  selectCurrentWorkflow,
  selectWorkflowVersion,
  selectEdges,
  selectTriggers,
  selectActivities,
} from '../../stores/useWorkflowStore'
import { collectAllActivityIds } from '../../stores/workflowActivityHelpers'
import { detachPromise } from '../../utils/detachPromise'
import { buildTriggerNodeId, toPositionKey } from '../../utils/triggerNodeIds'
import { CanvasControls } from '../workflows/canvas/CanvasControls'
import { type NodeType } from '../workflows/canvas/nodes/NodeType'
import { UndoRedoControls } from '../workflows/canvas/UndoRedoControls'
import { useExecutionStore } from '../workflows/stores/useExecutionStore'

import { ActiveExecutionContext } from './ActiveExecutionContext'
import styles from './BuilderFlow.module.css'
import { builderEdgeTypes, builderNodeTypes, resolveExecutionStatus } from './builderFlowConfig'
import { BUTTON_EDGE_DEFAULT_STROKE } from './edges/buttonEdgeStrokeColor'
import { EdgeMarkers } from './edges/edgeMarkers'
import { useIsExecutionView } from './ExecutionViewContext'
import { useBuilderFlowGraph, executionStateEnricher } from './hooks/useBuilderFlowGraph'
import { useButtonEdgeMaintenance } from './hooks/useButtonEdgeMaintenance'
import { useConnectionHandlers } from './hooks/useConnectionHandlers'
import { useEdgeActiveState } from './hooks/useEdgeActiveState'
import { useEdgeExecutionStatus } from './hooks/useEdgeExecutionStatus'
import { useEdgeSynchronization } from './hooks/useEdgeSynchronization'
import { useExternalNodeSelection } from './hooks/useExternalNodeSelection'
import { useLoopBackNodeTypes } from './hooks/useLoopBackNodeTypes'
import { useNodeDeletion } from './hooks/useNodeDeletion'
import { useNodePositioning } from './hooks/useNodePositioning'
import { useNodeUpdates } from './hooks/useNodeUpdates'
import { usePendingEdgeManagement } from './hooks/usePendingEdgeManagement'
import { usePositionEventHandlers } from './hooks/usePositionEventHandlers'
import { useValidationEnrichment } from './hooks/useValidationEnrichment'
import { useWorkflowInitialization } from './hooks/useWorkflowInitialization'
import type { BuilderFlowProps, PendingEdge } from './types'
import { validateConnection } from './utils/validateConnection'
import { markerEnd, type EdgeType } from './utils/workflowToGraph'

const TERMINAL_EXECUTION_STATUSES = new Set(['completed', 'completed_with_errors', 'failed', 'cancelled'])

// eslint-disable-next-line max-lines-per-function, complexity
export function BuilderFlow(props: BuilderFlowProps) {
  const isExecutionView = useIsExecutionView()
  // Destructure props to use in callbacks
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

  // Use typed selectors for optimized subscriptions
  const workflowVersion = useWorkflowStore(selectWorkflowVersion)
  const currentWorkflow = useWorkflowStore(selectCurrentWorkflow)
  const storedEdges = useWorkflowStore(selectEdges)
  // Subscribe to triggers array to detect when triggers are added/removed/updated
  const triggers = useWorkflowStore(selectTriggers)
  // Subscribe to activities array directly to detect updates to individual activities
  const activities = useWorkflowStore(selectActivities)
  // Access actions without subscribing to state changes
  const { setEdges: setStoredEdges, updateNodePositions } = useWorkflowStoreActions()
  const reactFlowInstance = useReactFlow()
  const { showError } = useAlerts()
  const { fitView, getViewport, screenToFlowPosition, updateNode } = reactFlowInstance
  const containerRef = useRef<HTMLDivElement>(null)

  const activityStates = useExecutionStore((state) => state.activityStates)
  const executionMetadata = useExecutionStore((state) => state.executionMetadata)
  const preResolvedNodes = useMemo(
    () => new Set(Object.keys(executionMetadata?.pre_resolved_nodes ?? {})),
    [executionMetadata]
  )
  const storeExecutionStatus = useExecutionStore((state) => state.visualization?.status)
  const effectiveExecutionStatus = resolveExecutionStatus(executionStatus, storeExecutionStatus)
  const isActiveExecution =
    effectiveExecutionStatus !== null && !TERMINAL_EXECUTION_STATUSES.has(effectiveExecutionStatus)
  const isReadOnly = isExecutionView || isActiveExecution || readOnlyProp || !canEdit
  // Button-edge maintenance must also see null for terminal states so it recreates the "+" buttons.
  const buttonEdgeExecutionStatus = isActiveExecution ? effectiveExecutionStatus : null

  // Track pending edge that was dragged to canvas
  const [pendingEdge, setPendingEdge] = useState<PendingEdge | null>(null)

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

  // CRITICAL FIX: Use controlled state instead of useNodesState/useEdgesState
  // React Flow's hooks reset state when initialNodes/initialEdges change
  // This causes ButtonEdges to be lost when workflow store updates trigger initialEdges recomputation
  // Solution: Initialize once on mount, then manage state independently
  const isInitializedRef = useRef(false)
  const lastWorkflowIdRef = useRef<string | null>(workflowId)
  const lastWorkflowVersionRef = useRef<number>(workflowVersion)
  const initialNodesRef = useRef(initialNodes)
  initialNodesRef.current = initialNodes
  const initialEdgesRef = useRef(initialEdges)
  initialEdgesRef.current = initialEdges
  const [nodes, setNodes] = useState<NodeType[]>([])

  const [edges, setEdges] = useState<EdgeType[]>([])

  // Track when we're in the middle of a deletion operation to prevent re-initialization
  const isDeletingRef = useRef(false)

  // Reset initialization flag when workflow ID changes, version changes, OR when workflow is cleared
  // This handles navigation to different workflows, fresh data loading, AND BuilderContent's cleanup
  useEffect(() => {
    const currentWorkflow = useWorkflowStore.getState().currentWorkflow
    const workflowIdChanged = workflowId !== lastWorkflowIdRef.current
    const workflowVersionChanged = workflowVersion !== lastWorkflowVersionRef.current
    const workflowCleared = !currentWorkflow && isInitializedRef.current

    if (workflowIdChanged) {
      // CRITICAL: Reset initialization flag BEFORE clearing state
      // This ensures the initialization effect will run after state is cleared
      isInitializedRef.current = false

      // CRITICAL: Clear nodes and edges state when switching to a different workflow
      // This ensures old workflow's edges don't persist in React Flow
      setNodes([])

      setEdges([])

      // CRITICAL: Update refs AFTER clearing state
      lastWorkflowIdRef.current = workflowId
      lastWorkflowVersionRef.current = workflowVersion
    } else if (workflowVersionChanged) {
      // Workflow version changed (fresh data loaded or undo/redo) — re-initialize.
      // Directly set correct nodes/edges instead of clearing to empty. Clearing
      // and relying on the init effect to re-populate creates a window where any
      // condition failure in the init effect leaves the canvas permanently blank.
      isInitializedRef.current = false
      const { nodePositions: positions, currentWorkflow } = useWorkflowStore.getState()
      const trigs = currentWorkflow?.triggers ?? []
      const currentInitialNodes = initialNodesRef.current
      const nodesWithPositions =
        Object.keys(positions).length > 0
          ? currentInitialNodes.map((n) => {
              const stored = positions[toPositionKey(n.id, trigs)]
              return stored ? { ...n, position: stored } : n
            })
          : currentInitialNodes
      setNodes(nodesWithPositions)
      setEdges(initialEdgesRef.current)
      lastWorkflowVersionRef.current = workflowVersion
    } else if (workflowCleared) {
      // Workflow was cleared from store (by BuilderContent cleanup) but ID didn't change
      // Reset initialization so we re-initialize when workflow loads again
      isInitializedRef.current = false

      setNodes([])

      setEdges([])
    }
  }, [workflowId, workflowVersion])

  // Initialize nodes and edges only once per workflow
  // CRITICAL: Skip initialization if we're in the middle of a deletion operation
  // This prevents re-initialization when storedEdges changes during node deletion
  // CRITICAL: Also check that workflow exists in store to prevent race condition when switching workflows
  // During workflow switch, store is cleared but useMemo might not have re-run yet with empty edges
  // CRITICAL: Only initialize if workflowId matches lastWorkflowIdRef - prevents initializing with old workflow data
  useEffect(() => {
    const currentWorkflow = useWorkflowStore.getState().currentWorkflow
    const hasWorkflow = !!currentWorkflow
    const isCorrectWorkflow = lastWorkflowIdRef.current === workflowId

    // CRITICAL: If workflow has activities, it should have edges
    // Wait for edges to be loaded before initializing
    const hasActivities = (currentWorkflow?.workflow?.activities?.length ?? 0) > 0
    if (hasWorkflow && hasActivities && initialEdges.length === 0) {
      // Workflow has activities but no edges yet - wait for edges to load
      return
    }

    // CRITICAL: Validate that edges actually belong to this workflow
    // Check if edge references match activity IDs in the workflow
    let edgesMatchWorkflow = true // Default true for empty workflows
    if (hasWorkflow && initialEdges.length > 0) {
      const activityIds = collectAllActivityIds(currentWorkflow.workflow.activities)
      const triggers = currentWorkflow.triggers ?? []
      triggers.forEach((_: unknown, index: number) => {
        activityIds.add(buildTriggerNodeId(index))
      })

      // CRITICAL: Check if ALL edges reference activities in this workflow
      // If ANY edge references an activity not in this workflow, edges are stale
      const allEdgesValid = initialEdges.every((edge) => {
        const sourceValid =
          edge.source != null && (activityIds.has(edge.source) || edge.source.startsWith('placeholder-'))
        const targetValid =
          edge.target != null && (activityIds.has(edge.target) || edge.target.startsWith('placeholder-'))
        return sourceValid && targetValid
      })
      edgesMatchWorkflow = allEdgesValid
    }

    // CRITICAL: Initialize if we have a workflow with nodes
    // Allow initialization even with no edges (for new empty workflows)
    // For workflows with edges, validate that edges match the workflow activities
    if (
      !isInitializedRef.current &&
      !isDeletingRef.current &&
      hasWorkflow &&
      isCorrectWorkflow &&
      initialNodes.length > 0 &&
      edgesMatchWorkflow
    ) {
      // Apply stored positions (restored by undo/redo or saved after layout).
      const positions = useWorkflowStore.getState().nodePositions
      const trigs = currentWorkflow?.triggers ?? []
      const nodesWithPositions =
        Object.keys(positions).length > 0
          ? initialNodes.map((n) => {
              const stored = positions[toPositionKey(n.id, trigs)]
              return stored ? { ...n, position: stored } : n
            })
          : initialNodes

      setNodes(nodesWithPositions)

      setEdges(initialEdges)
      isInitializedRef.current = true
    }
  }, [initialNodes, initialEdges, workflowId, workflowVersion])

  // Apply React Flow node changes (position, selection, etc.) to local state.
  // Drag-end positions are persisted to the store via onNodeDragStop instead
  // of here, because onNodesChange drag-end events may omit the final position
  // for some node types (e.g. loop nodes).
  const onNodesChange = useCallback(
    (changes: NodeChange<NodeType>[]) => {
      const filtered = isReadOnly
        ? changes.filter((c) => c.type === 'dimensions' || c.type === 'position' || c.type === 'select')
        : changes
      setNodes((nds) => applyNodeChanges(filtered, nds))
    },
    [isReadOnly]
  )

  useExternalNodeSelection(selectedActivityId, setNodes)

  const { onNodeDragStop, onLayout } = usePositionEventHandlers(nodes, edges, setNodes, setEdges)

  const onEdgesChange = useCallback(
    (changes: EdgeChange<EdgeType>[]) => {
      if (isReadOnly) return
      setEdges((eds) => applyEdgeChanges(changes, eds))
    },
    [isReadOnly]
  )

  const hasStoredPositions = useMemo(
    () => Object.keys(useWorkflowStore.getState().nodePositions).length > 0,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [workflowVersion]
  )
  const clearUndoHistory = useCallback(() => {
    const temporal = useWorkflowStore.temporal.getState()
    if (useWorkflowStore.getState()._preserveHistoryOnLayout) {
      useWorkflowStore.setState({ _preserveHistoryOnLayout: false })
    } else {
      temporal.pause()
      temporal.clear()
    }
    // Resume after React has settled (edge sync, button edge maintenance, etc.)
    // so that post-layout derived store updates don't create spurious undo entries.
    setTimeout(() => temporal.resume(), 200)
  }, [])
  const { isInitialized } = useWorkflowInitialization({
    nodes,
    workflowVersion,
    onLayout,
    hasStoredPositions,
    onAfterInitialLayout: clearUndoHistory,
  })

  // Use custom hook to manage node and edge updates
  const { newlyAddedNodeIdsRef } = useNodeUpdates({
    initialNodes,
    initialEdges,
    isInitialized,
    setNodes,
    setEdges,
    workflowVersion,
  })

  // Use custom hook to synchronize edges with workflow store
  useEdgeSynchronization({
    edges,
    isInitialized,
    setStoredEdges,
    workflowVersion,
    isActiveExecution,
  })

  useLoopBackNodeTypes({ edges, isInitialized, setNodes })

  // Use custom hook for node deletion handling
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

  // Use custom hook for node positioning
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

  useEffect(() => {
    if (isInitialized) {
      const timer = setTimeout(() => {
        detachPromise(fitView({ duration: 300, padding: 0.1 }))
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [panelOpen, fitView, isInitialized])

  // Use custom hook for connection handling
  const { onConnect, onConnectStart, onConnectEnd } = useConnectionHandlers({
    nodes,
    edges,
    onAddNodeFromEdge,
    setNodes,
    setEdges,
    setPendingEdge,
    screenToFlowPosition,
  })

  // Use custom hook to maintain button edges on nodes
  // Skip button edges in execution view mode
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

  // Use custom hook to manage edge active states
  useEdgeActiveState({
    isInitialized,
    activeEdgeId: activeEdgeId ?? null,
    activeEdgeButtonNodeId: activeEdgeButtonNodeId ?? null,
    activeEdgeButtonHandle: activeEdgeButtonHandle ?? null,
    onAddNodeFromEdge,
    setEdges,
  })

  useEffect(() => {
    if (!panelOpen && pendingEdge) {
      setPendingEdge(null)
    }
    if (pendingEdge) {
      const sourceExists = nodes.some((n) => n.id === pendingEdge.sourceNodeId)
      if (!sourceExists) {
        setPendingEdge(null)
      }
    }
  }, [panelOpen, pendingEdge, nodes])

  usePendingEdgeManagement({
    pendingEdge,
    isInitialized,
    setNodes,
    setEdges,
  })

  // Helper to check if execution state changed (shallow comparison)
  const hasExecutionStateChanged = useCallback(
    (
      currentState: { status?: string; started_at?: string; completed_at?: string } | undefined,
      newState: { status?: string; started_at?: string; completed_at?: string } | undefined
    ): boolean => {
      return (
        currentState !== newState &&
        (currentState?.status !== newState?.status ||
          currentState?.started_at !== newState?.started_at ||
          currentState?.completed_at !== newState?.completed_at)
      )
    },
    []
  )

  /**
   * Apply enriched data to a node if execution state changed.
   * Centralizes the state extraction, comparison, and node update logic.
   */
  const applyEnrichedData = useCallback(
    (node: NodeType, enriched: Record<string, unknown>, anyChangedRef: { current: boolean }): NodeType => {
      const currentState = (node.data as Record<string, unknown>).__executionState as
        | { status?: string; started_at?: string; completed_at?: string }
        | undefined
      const newState = enriched.__executionState as
        | { status?: string; started_at?: string; completed_at?: string }
        | undefined
      if (hasExecutionStateChanged(currentState, newState)) {
        anyChangedRef.current = true
        return { ...node, data: enriched } as unknown as NodeType
      }
      return node
    },
    [hasExecutionStateChanged]
  )

  // Update node execution state when activity states change (e.g., after REST load or WebSocket)
  // Also clear node execution status when returning to edit mode
  useEffect(() => {
    if (!isInitialized) return

    // In edit mode (effectiveExecutionStatus is null), clear all execution states
    if (!effectiveExecutionStatus) {
      setNodes((currentNodes) => {
        const hasExecutionState = currentNodes.some((node) => (node.data as Record<string, unknown>).__executionState)
        if (!hasExecutionState) return currentNodes

        return currentNodes.map((node) => {
          const currentData = node.data as Record<string, unknown>
          if (currentData.__executionState) {
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            const { __executionState, ...rest } = currentData
            return { ...node, data: rest } as unknown as NodeType
          }
          return node
        })
      })
      return
    }

    // In execution mode, enrich nodes with execution state
    if (activityStates.size === 0) return

    const activities = currentWorkflow?.workflow.activities ?? []
    const triggers = currentWorkflow?.triggers ?? []
    const activitiesById = new Map(activities.map((a) => [a.id, a]))
    const edgeSnapshot = useWorkflowStore.getState().edges

    setNodes((currentNodes) => {
      const anyChangedRef = { current: false }
      const updatedNodes = currentNodes.map((node) => {
        if (node.id.startsWith('trigger-')) {
          const triggerRealId = triggers[Number.parseInt(node.id.split('-')[1], 10)]?.id
          const enriched = executionStateEnricher.enrichTriggerNode(
            triggerRealId,
            node.data as Record<string, unknown>,
            effectiveExecutionStatus,
            activityStates
          )
          return applyEnrichedData(node, enriched, anyChangedRef)
        }
        const activity = activitiesById.get(node.id)
        if (!activity) return node
        const enriched = executionStateEnricher.enrichActivity(
          activity,
          effectiveExecutionStatus,
          activityStates,
          edgeSnapshot,
          { preResolvedNodes, skipInferenceActivityIds: copiedRunActivityIds ?? undefined }
        )
        return applyEnrichedData(node, enriched, anyChangedRef)
      })

      // Only return new array if something actually changed
      return anyChangedRef.current ? updatedNodes : currentNodes
    })
  }, [
    activityStates,
    effectiveExecutionStatus,
    isInitialized,
    currentWorkflow,
    applyEnrichedData,
    preResolvedNodes,
    copiedRunActivityIds,
  ])

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

  const isValidConnection = useCallback(
    (connection: EdgeType | Connection) => validateConnection(connection, edges),
    [edges]
  )

  return (
    <ActiveExecutionContext.Provider value={isActiveExecution}>
      <div
        ref={containerRef}
        className={readOnlyProp ? styles.readonlyCanvas : undefined}
        style={{
          width: '100%',
          height: '100%',
          position: 'relative',
        }}
      >
        {effectiveExecutionStatus === 'running' && (
          <div
            style={{
              position: 'absolute',
              top: 'var(--pf-t--global--spacer--md)',
              left: 'var(--pf-t--global--spacer--md)',
              zIndex: 1000,
            }}
          >
            <Spinner
              size="xl"
              style={
                { '--pf-v6-c-spinner--Color': 'var(--pf-t--global--color--brand--default)' } as React.CSSProperties
              }
            />
          </div>
        )}
        <ReactFlow<NodeType, EdgeType>
          nodes={nodes}
          edges={edges}
          nodeTypes={builderNodeTypes}
          edgeTypes={builderEdgeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStop={isReadOnly ? undefined : onNodeDragStop}
          onEdgesChange={onEdgesChange}
          onNodesDelete={isReadOnly ? undefined : onNodesDelete}
          onNodeClick={!canEdit && !isExecutionView ? undefined : onNodeClick}
          onConnect={isReadOnly ? undefined : onConnect}
          onConnectStart={isReadOnly ? undefined : onConnectStart}
          onConnectEnd={isReadOnly ? undefined : onConnectEnd}
          connectOnClick={false}
          connectionRadius={200}
          connectionLineStyle={{ stroke: BUTTON_EDGE_DEFAULT_STROKE, strokeWidth: 2 }}
          connectionLineType={ConnectionLineType.SmoothStep}
          defaultEdgeOptions={{ markerEnd }}
          isValidConnection={isValidConnection}
          proOptions={{ hideAttribution: true }}
          deleteKeyCode={isReadOnly || disableDeleteKey ? null : ['Delete', 'Backspace']}
          panActivationKeyCode={disableSpacePanning ? null : 'Space'}
          fitView
          minZoom={0.1}
          maxZoom={1}
          nodesDraggable={!isReadOnly}
          nodesConnectable={!isReadOnly}
        >
          <EdgeMarkers />
          {!isReadOnly && <Background variant={BackgroundVariant.Dots} gap={20} size={1} />}
          <CanvasControls onLayout={onLayout} hideLayout={isReadOnly} />
          {!isReadOnly && <UndoRedoControls />}
        </ReactFlow>
      </div>
    </ActiveExecutionContext.Provider>
  )
}
