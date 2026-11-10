import { Spinner } from '@patternfly/react-core'
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  NodeToolbar,
  Position,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeMouseHandler,
  type OnConnectEnd,
  type OnConnectStart,
  type OnNodeDrag,
  type OnNodesDelete,
  type ReactFlowState,
  useStore,
  useUpdateNodeInternals,
} from '@xyflow/react'
import { useLayoutEffect, useMemo, useRef } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'
import { FlowNodeType } from '../../constants'
import { CanvasControls } from '../workflows/canvas/CanvasControls'
import { type NodeType } from '../workflows/canvas/nodes/NodeType'
import { SEMANTIC_ZOOM_MAX_SCALE } from '../workflows/canvas/semanticZoom'
import { UndoRedoControls } from '../workflows/canvas/UndoRedoControls'

import styles from './BuilderFlow.module.css'
import canvasStyles from './BuilderFlowCanvas.module.css'
import { builderEdgeTypes, builderNodeTypes } from './builderFlowConfig'
import { BUTTON_EDGE_DEFAULT_STROKE } from './edges/buttonEdgeStrokeColor'
import { EdgeMarkers } from './edges/edgeMarkers'
import { getRetryPreviewCanvasStates, type RetryPreviewCanvasState } from './retryPreviewCanvasState'
import { getRetryPreviewLabelPlacements, RETRY_LABEL_BASE_OFFSET, type RetryLabelSide } from './retryPreviewLabelLayout'
import { markerEnd, type EdgeType } from './utils/workflowToGraph'

type BuilderFlowCanvasProps = {
  containerRef: React.RefObject<HTMLDivElement | null>
  readOnlyProp?: boolean
  effectiveExecutionStatus: string | null
  isReadOnly: boolean
  nodes: NodeType[]
  retryPreviewNodeIds?: readonly string[]
  edges: EdgeType[]
  onNodesChange: (changes: NodeChange<NodeType>[]) => void
  onNodeDragStart?: OnNodeDrag<NodeType>
  onNodeDrag?: OnNodeDrag<NodeType>
  onNodeDragStop?: OnNodeDrag<NodeType>
  onEdgesChange: (changes: EdgeChange<EdgeType>[]) => void
  onNodesDelete?: OnNodesDelete<NodeType>
  onNodeClick?: NodeMouseHandler<NodeType>
  onConnect?: (connection: Connection) => void
  onConnectStart?: OnConnectStart
  onConnectEnd?: OnConnectEnd
  isValidConnection: (connection: EdgeType | Connection) => boolean
  disableDeleteKey?: boolean
  disableSpacePanning?: boolean
  onLayout: () => void
}

type SemanticZoomStoreState = {
  isSemanticZoom: boolean
  nodeIds: string[]
}

/** Reads whether the canvas is at or below the semantic-zoom scale, and the IDs of its non-placeholder nodes. */
function selectSemanticZoomStoreState(state: ReactFlowState): SemanticZoomStoreState {
  return {
    isSemanticZoom: state.transform[2] <= SEMANTIC_ZOOM_MAX_SCALE,
    nodeIds: state.nodes.filter((node) => node.type !== FlowNodeType.PLACEHOLDER).map((node) => node.id),
  }
}

/** Equality check for the selector above, so the store only notifies on a real threshold or node-set change. */
function semanticZoomStoreStateEqual(previous: SemanticZoomStoreState, next: SemanticZoomStoreState): boolean {
  // Dimension updates replace node objects; only IDs and threshold transitions require another measurement.
  return (
    previous.isSemanticZoom === next.isSemanticZoom &&
    previous.nodeIds.length === next.nodeIds.length &&
    previous.nodeIds.every((nodeId, index) => nodeId === next.nodeIds[index])
  )
}

/**
 * Batches `updateNodeInternals` for all visible nodes in one call when semantic zoom is entered, exited, or
 * when the node set changes while semantic zoom is active, instead of recomputing internals per node per render.
 */
function SemanticZoomNodeInternalsUpdater() {
  const { isSemanticZoom, nodeIds } = useStore(selectSemanticZoomStoreState, semanticZoomStoreStateEqual)
  const updateNodeInternals = useUpdateNodeInternals()
  const previousSemanticZoomRef = useRef<boolean | undefined>(undefined)

  useLayoutEffect(() => {
    const previousSemanticZoom = previousSemanticZoomRef.current
    previousSemanticZoomRef.current = isSemanticZoom

    const mountedInSemanticZoom = previousSemanticZoom === undefined && isSemanticZoom
    const crossedSemanticZoomThreshold = previousSemanticZoom !== undefined && previousSemanticZoom !== isSemanticZoom
    const nodeIdsChangedDuringSemanticZoom = previousSemanticZoom === isSemanticZoom && isSemanticZoom

    if (
      (mountedInSemanticZoom || crossedSemanticZoomThreshold || nodeIdsChangedDuringSemanticZoom) &&
      nodeIds.length > 0
    ) {
      updateNodeInternals(nodeIds)
    }
  }, [isSemanticZoom, nodeIds, updateNodeInternals])

  return null
}

export function BuilderFlowCanvas({
  containerRef,
  readOnlyProp,
  effectiveExecutionStatus,
  isReadOnly,
  nodes,
  retryPreviewNodeIds = [],
  edges,
  onNodesChange,
  onNodeDragStart,
  onNodeDrag,
  onNodeDragStop,
  onEdgesChange,
  onNodesDelete,
  onNodeClick,
  onConnect,
  onConnectStart,
  onConnectEnd,
  isValidConnection,
  disableDeleteKey,
  disableSpacePanning,
  onLayout,
}: Readonly<BuilderFlowCanvasProps>) {
  const retryPreviewCanvasStates = useMemo(
    () =>
      getRetryPreviewCanvasStates(
        nodes.map((node) => ({ id: node.id, type: node.type, status: getNodeExecutionStatus(node) })),
        edges,
        retryPreviewNodeIds
      ),
    [edges, nodes, retryPreviewNodeIds]
  )
  const accessibleNodes = useMemo(
    () =>
      nodes.map((node) => {
        const retryState = retryPreviewCanvasStates.get(node.id)
        if (!retryState) return node

        const nodeName = 'name' in node.data && typeof node.data.name === 'string' ? node.data.name : node.id
        const stateLabel = getRetryStateAccessibleLabel(retryState)
        const ariaLabel = `${node.ariaLabel ?? nodeName}, ${stateLabel}`
        if (retryState === 'origin') return { ...withRetryPreviewOrigin(node), ariaLabel }
        return {
          ...node,
          ariaLabel,
        }
      }),
    [nodes, retryPreviewCanvasStates]
  )
  const zoom = useStore((state: ReactFlowState) => state.transform[2])
  const retryLabelPlacements = useMemo(
    () => getRetryPreviewLabelPlacements(nodes, retryPreviewCanvasStates, zoom),
    [nodes, retryPreviewCanvasStates, zoom]
  )

  return (
    <div
      ref={containerRef}
      className={
        readOnlyProp ? `${canvasStyles.canvasContainer} ${styles.readonlyCanvas}` : canvasStyles.canvasContainer
      }
    >
      {effectiveExecutionStatus === 'running' && (
        <div className={canvasStyles.executionSpinner}>
          <Spinner size="xl" className={canvasStyles.executionSpinnerIcon} />
        </div>
      )}
      <ReactFlow<NodeType, EdgeType>
        nodes={accessibleNodes}
        edges={edges}
        nodeTypes={builderNodeTypes}
        edgeTypes={builderEdgeTypes}
        onNodesChange={onNodesChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onEdgesChange={onEdgesChange}
        onNodesDelete={onNodesDelete}
        onNodeClick={onNodeClick}
        onConnect={onConnect}
        onConnectStart={onConnectStart}
        onConnectEnd={onConnectEnd}
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
        <SemanticZoomNodeInternalsUpdater />
        <EdgeMarkers />
        {retryPreviewNodeIds.map((nodeId) => (
          <NodeToolbar
            key={nodeId}
            nodeId={nodeId}
            isVisible
            position={retryLabelToolbarPosition(retryLabelPlacements.get(nodeId)?.side)}
            align={retryLabelPlacements.get(nodeId)?.align ?? 'center'}
            offset={retryLabelPlacements.get(nodeId)?.offset ?? RETRY_LABEL_BASE_OFFSET}
            data-testid={`retry-origin-${nodeId}`}
          >
            <span
              className={canvasStyles.retryPreviewLabel}
              data-testid={`retry-origin-label-${nodeId}`}
              aria-hidden="true"
            >
              <SynLabel color="blue">Retry origin</SynLabel>
            </span>
          </NodeToolbar>
        ))}
        {[...retryPreviewCanvasStates].map(([nodeId, state]) => {
          if (state === 'origin') return null
          return (
            <NodeToolbar
              key={`retry-state-${nodeId}`}
              nodeId={nodeId}
              isVisible
              position={retryLabelToolbarPosition(retryLabelPlacements.get(nodeId)?.side)}
              align={retryLabelPlacements.get(nodeId)?.align ?? 'center'}
              offset={retryLabelPlacements.get(nodeId)?.offset ?? RETRY_LABEL_BASE_OFFSET}
              data-testid={`retry-state-${nodeId}`}
            >
              <span
                className={canvasStyles.retryPreviewLabel}
                data-testid={`retry-state-label-${nodeId}`}
                aria-hidden="true"
              >
                <RetryStateLabel state={state} />
              </span>
            </NodeToolbar>
          )
        })}
        {!isReadOnly && <Background variant={BackgroundVariant.Dots} gap={20} size={1} />}
        <CanvasControls onLayout={onLayout} hideLayout={isReadOnly} />
        {!isReadOnly && <UndoRedoControls />}
      </ReactFlow>
    </div>
  )
}

function getNodeExecutionStatus(node: NodeType): string | undefined {
  const data = node.data as Record<string, unknown>
  const executionState = data.__executionState
  if (!executionState || typeof executionState !== 'object' || !('status' in executionState)) return undefined
  return typeof executionState.status === 'string' ? executionState.status : undefined
}

function getRetryStateAccessibleLabel(state: RetryPreviewCanvasState): string {
  switch (state) {
    case 'origin':
      return 'retry origin'
    case 'will-retry':
      return 'in retry scope'
    case 'retained':
      return 'retains prior result'
    case 'not-retried':
      return 'not retried; remains failed'
  }
}

function RetryStateLabel({ state }: Readonly<{ state: Exclude<RetryPreviewCanvasState, 'origin'> }>) {
  if (state === 'will-retry') return <SynLabel color="blue">In retry scope</SynLabel>
  if (state === 'retained') return <SynLabel color="grey">Retains prior result</SynLabel>
  return <SynLabel color="orange">Not retried — remains failed</SynLabel>
}

function retryLabelToolbarPosition(side: RetryLabelSide | undefined): Position {
  if (side === 'left') return Position.Left
  if (side === 'right') return Position.Right
  return Position.Top
}

function withRetryPreviewOrigin<T extends NodeType>(node: T): T & { data: T['data'] & { __retryPreviewOrigin: true } } {
  return {
    ...node,
    data: Object.assign({}, node.data, { __retryPreviewOrigin: true as const }),
  }
}
