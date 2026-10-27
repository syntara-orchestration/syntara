import { Content, Spinner } from '@patternfly/react-core'
import {
  Background,
  BackgroundVariant,
  ConnectionLineType,
  ReactFlow,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type NodeMouseHandler,
  type OnBeforeDelete,
  type OnConnectEnd,
  type OnConnectStart,
  type OnNodeDrag,
  type OnNodesDelete,
  type ReactFlowState,
  useStore,
  useUpdateNodeInternals,
} from '@xyflow/react'
import { useCallback, useLayoutEffect, useRef } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'
import { FlowNodeType } from '../../constants'
import { useDialogState } from '../../hooks/useDialogState'
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

type PendingNodeDeletion = {
  nodeCount: number
  resolve: (confirmed: boolean) => void
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
  const {
    isOpen: isDeleteDialogOpen,
    item: pendingDeletion,
    open: openDeleteDialog,
    close: closeDeleteDialog,
  } = useDialogState<PendingNodeDeletion>()
  const onBeforeDelete = useCallback<OnBeforeDelete<NodeType, EdgeType>>(
    ({ nodes: nodesToDelete }) => {
      if (isReadOnly || isDeleteDialogOpen) return Promise.resolve(false)
      if (nodesToDelete.length === 0) return Promise.resolve(true)

      return new Promise<boolean>((resolve) => {
        openDeleteDialog({ nodeCount: nodesToDelete.length, resolve })
      })
    },
    [isReadOnly, isDeleteDialogOpen, openDeleteDialog]
  )
  const resolveDeletion = (confirmed: boolean) => {
    pendingDeletion?.resolve(confirmed && !isReadOnly)
    closeDeleteDialog()
  }
  const isMultiDelete = (pendingDeletion?.nodeCount ?? 0) > 1

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
        onBeforeDelete={onBeforeDelete}
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
      <SynConfirmationDialog
        isOpen={isDeleteDialogOpen}
        onClose={() => resolveDeletion(false)}
        onConfirm={() => resolveDeletion(true)}
        title={isMultiDelete ? 'Delete steps?' : 'Delete step?'}
        confirmLabel="Delete"
        confirmVariant="danger"
        titleIconVariant="warning"
      >
        <Content component="p">
          {isMultiDelete
            ? 'The selected steps and their connections will be deleted from this workflow.'
            : 'The selected step and its connections will be deleted from this workflow.'}{' '}
          You can undo this action.
        </Content>
      </SynConfirmationDialog>
    </div>
  )
}
