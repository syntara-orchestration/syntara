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
        edgesFocusable={false}
      >
        <SemanticZoomNodeInternalsUpdater />
        <EdgeMarkers />
        <RetryPreviewNodeToolbars
          nodes={nodes}
          retryPreviewNodeIds={retryPreviewNodeIds}
          states={retryPreviewCanvasStates}
        />
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

type RetryLabelBounds = Readonly<{ left: number; right: number; top: number; bottom: number }>

const RETRY_LABEL_HEIGHT = 22
const RETRY_LABEL_BASE_OFFSET = 8
const RETRY_LABEL_LANE_GAP = 6
const DEFAULT_NODE_WIDTH = 300
const DEFAULT_NODE_HEIGHT = 120

function retryStateLabelText(state: RetryPreviewCanvasState): string {
  switch (state) {
    case 'origin':
      return 'Retry origin'
    case 'will-retry':
      return 'In retry scope'
    case 'retained':
      return 'Retains prior result'
    case 'not-retried':
      return 'Not retried — remains failed'
  }
}

function withRetryPreviewOrigin<T extends NodeType>(node: T): T & { data: T['data'] & { __retryPreviewOrigin: true } } {
  return {
    ...node,
    data: Object.assign({}, node.data, { __retryPreviewOrigin: true as const }),
  }
}

function overlaps(left: RetryLabelBounds, right: RetryLabelBounds): boolean {
  return left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top
}

/** Place retry labels above nodes and move overlapping labels into separate lanes. */
function getRetryPreviewLabelOffsets(
  nodes: readonly NodeType[],
  states: ReadonlyMap<string, RetryPreviewCanvasState>,
  zoom: number
): Map<string, number> {
  const nodesById = new Map(nodes.map((node) => [node.id, node]))
  const absolutePositionById = new Map<string, { x: number; y: number }>()

  function getAbsolutePosition(node: NodeType, visited = new Set<string>()): { x: number; y: number } {
    const knownPosition = absolutePositionById.get(node.id)
    if (knownPosition) return knownPosition
    if (!node.parentId || visited.has(node.parentId)) return node.position

    const parent = nodesById.get(node.parentId)
    if (!parent) return node.position

    visited.add(node.id)
    const parentPosition = getAbsolutePosition(parent, visited)
    const position = { x: parentPosition.x + node.position.x, y: parentPosition.y + node.position.y }
    absolutePositionById.set(node.id, position)
    return position
  }

  const nodeBounds = nodes.map((node) => {
    const position = getAbsolutePosition(node)
    const width = node.measured?.width ?? node.width ?? DEFAULT_NODE_WIDTH
    const height = node.measured?.height ?? node.height ?? DEFAULT_NODE_HEIGHT
    const left = position.x * zoom
    const top = position.y * zoom
    return { left, right: left + width * zoom, top, bottom: top + height * zoom }
  })
  const labelEntries = [...states]
    .map(([nodeId, state]) => {
      const node = nodesById.get(nodeId)
      if (!node) return undefined
      const position = getAbsolutePosition(node)
      const width = node.measured?.width ?? node.width ?? DEFAULT_NODE_WIDTH
      const center = (position.x + width / 2) * zoom
      const labelWidth = retryStateLabelText(state).length * 7 + 20
      return { nodeId, center, top: position.y * zoom, width: labelWidth }
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== undefined)
    .sort((left, right) => left.top - right.top || left.center - right.center)

  const offsets = new Map<string, number>()
  const placedLabels: RetryLabelBounds[] = []

  for (const entry of labelEntries) {
    let lane = 0
    let bounds: RetryLabelBounds
    let offset: number
    do {
      offset = RETRY_LABEL_BASE_OFFSET + lane * (RETRY_LABEL_HEIGHT + RETRY_LABEL_LANE_GAP)
      const bottom = entry.top - offset
      bounds = {
        left: entry.center - entry.width / 2,
        right: entry.center + entry.width / 2,
        top: bottom - RETRY_LABEL_HEIGHT,
        bottom,
      }
      lane += 1
    } while (
      nodeBounds.some((nodeBoundsEntry) => overlaps(bounds, nodeBoundsEntry)) ||
      placedLabels.some((placed) => overlaps(bounds, placed))
    )

    offsets.set(entry.nodeId, offset)
    placedLabels.push(bounds)
  }

  return offsets
}

function RetryPreviewNodeToolbars({
  nodes,
  retryPreviewNodeIds,
  states,
}: Readonly<{
  nodes: readonly NodeType[]
  retryPreviewNodeIds: readonly string[]
  states: ReadonlyMap<string, RetryPreviewCanvasState>
}>) {
  const zoom = useStore((state: ReactFlowState) => state.transform[2])
  const labelOffsets = useMemo(() => getRetryPreviewLabelOffsets(nodes, states, zoom), [nodes, states, zoom])

  return (
    <>
      {retryPreviewNodeIds.map((nodeId) => (
        <NodeToolbar
          key={nodeId}
          nodeId={nodeId}
          isVisible
          position={Position.Top}
          align="center"
          offset={labelOffsets.get(nodeId) ?? RETRY_LABEL_BASE_OFFSET}
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
      {[...states].map(([nodeId, state]) => {
        if (state === 'origin') return null
        return (
          <NodeToolbar
            key={`retry-state-${nodeId}`}
            nodeId={nodeId}
            isVisible
            position={Position.Top}
            align="center"
            offset={labelOffsets.get(nodeId) ?? RETRY_LABEL_BASE_OFFSET}
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
    </>
  )
}
