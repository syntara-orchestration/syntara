import type { NodeMouseHandler } from '@xyflow/react'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import type { ValidationError } from './builderReducer'

/** Flow coordinate (e.g. for node placement or edge end position) */
export type FlowPosition = { x: number; y: number }

/** Arguments for opening the add-node flow from an edge, button edge, or canvas drop. */
export type AddNodeFromEdgeOptions = {
  sourceNodeId: string
  targetNodeId?: string
  edgeId?: string
  sourceHandle?: string
  /** Places the new node's left edge at this flow coordinate when set */
  desiredPosition?: FlowPosition
}

export type OnAddNodeFromEdge = (options: AddNodeFromEdgeOptions) => void

/**
 * Props for the BuilderFlow component
 */
export type BuilderFlowProps = {
  /** Workflow ID from route params (null for new workflows) */
  workflowId?: string | null
  /** Whether the user has RBAC permission to edit. Defaults to `true` (execution view sets its own read-only). */
  canEdit?: boolean
  /** Whether the side panel is open */
  panelOpen?: boolean
  /** ID of the node whose button edge is currently active */
  activeEdgeButtonNodeId?: string | null
  /** Handle ID of the active button edge (for condition nodes: 'true' or 'false') */
  activeEdgeButtonHandle?: string | null
  /** ID of the currently active edge */
  activeEdgeId?: string | null
  /** Execution status for showing loading indicator */
  executionStatus?: string | null
  /**
   * Activity IDs from a copied run. When set, skip inference and execution badges
   * apply only to these IDs so nodes added after copy-to-editor have no status.
   */
  copiedRunActivityIds?: ReadonlySet<string> | null
  /** Handler for node click events */
  onNodeClick?: NodeMouseHandler<NodeType>
  /** Handler for adding a node from an edge; desiredPosition places the new node's left edge at that flow coordinate */
  onAddNodeFromEdge?: OnAddNodeFromEdge
  /** Desired position for the new node (e.g. from [+] click or pending edge drop); consumed by useNodePositioning */
  newNodeDesiredPosition?: FlowPosition | null
  /** Called when desired position has been applied so it can be cleared */
  onClearDesiredPosition?: () => void
  /** Handler called after nodes are deleted */
  onNodesDeleted?: (deletedNodeIds: string[]) => void
  /** Disable keyboard delete shortcuts (e.g., while editor overlay is open) */
  disableDeleteKey?: boolean
  /** Disable space key panning (e.g., while editor overlay with code editor is open) */
  disableSpacePanning?: boolean
  /** Force read-only mode (e.g., when viewing a historical version) */
  readOnly?: boolean
  /** Activity ID of the externally selected node (e.g. from table row click). */
  selectedActivityId?: string | null
  /** Validation errors from the verify workflow action */
  validationErrors?: ValidationError[]
}

/**
 * State for tracking connection attempts when dragging from a node
 */
export type ConnectionState = {
  sourceNodeId: string | null
  sourceHandleId: string | null
  successful: boolean
}

/**
 * Pending edge state when dragging from a node to the canvas
 */
export type PendingEdge = {
  sourceNodeId: string
  sourceHandle?: string
  x: number
  y: number
}
