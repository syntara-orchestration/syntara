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
} from '@xyflow/react'

import { CanvasControls } from '../workflows/canvas/CanvasControls'
import { type NodeType } from '../workflows/canvas/nodes/NodeType'
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
}: BuilderFlowCanvasProps) {
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
        <EdgeMarkers />
        {!isReadOnly && <Background variant={BackgroundVariant.Dots} gap={20} size={1} />}
        <CanvasControls onLayout={onLayout} hideLayout={isReadOnly} />
        {!isReadOnly && <UndoRedoControls />}
      </ReactFlow>
    </div>
  )
}
