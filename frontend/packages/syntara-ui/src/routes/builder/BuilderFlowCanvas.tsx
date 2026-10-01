import { Spinner } from '@patternfly/react-core'
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
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
import { useLayoutEffect, useRef } from 'react'

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
import { markerEnd, type EdgeType } from './utils/workflowToGraph'

type BuilderFlowCanvasProps = {
  containerRef: React.RefObject<HTMLDivElement | null>
  readOnlyProp?: boolean
  effectiveExecutionStatus: string | null
  isReadOnly: boolean
  nodes: NodeType[]
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

function selectSemanticZoomStoreState(state: ReactFlowState): SemanticZoomStoreState {
  return {
    isSemanticZoom: state.transform[2] <= SEMANTIC_ZOOM_MAX_SCALE,
    nodeIds: state.nodes.filter((node) => node.type !== FlowNodeType.PLACEHOLDER).map((node) => node.id),
  }
}

function semanticZoomStoreStateEqual(previous: SemanticZoomStoreState, next: SemanticZoomStoreState): boolean {
  // Dimension updates replace node objects; only IDs and threshold transitions require another measurement.
  return (
    previous.isSemanticZoom === next.isSemanticZoom &&
    previous.nodeIds.length === next.nodeIds.length &&
    previous.nodeIds.every((nodeId, index) => nodeId === next.nodeIds[index])
  )
}

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
        nodes={nodes}
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
        {!isReadOnly && <Background variant={BackgroundVariant.Dots} gap={20} size={1} />}
        <CanvasControls onLayout={onLayout} hideLayout={isReadOnly} />
        {!isReadOnly && <UndoRedoControls />}
      </ReactFlow>
    </div>
  )
}
