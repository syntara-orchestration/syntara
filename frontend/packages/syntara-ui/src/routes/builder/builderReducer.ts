import type { Node } from '@xyflow/react'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import {
  clearEditorAndOtherPanels,
  handleNodeClick,
  handlePanelActions,
  handleSimpleStateUpdate,
  handleValidationAction,
  PANEL_ACTIONS,
  SIMPLE_ACTIONS,
} from './builderReducerHandlers'
import type { FlowPosition } from './types'

export type ValidationSeverity = 'error' | 'warning'

/** Whether findings came from advisory save or an explicit verify/publish check. */
export type ValidationSource = 'save' | 'verify'

export type ValidationError = {
  message: string
  nodeId: string | null
  nodeName?: string
  severity?: ValidationSeverity
  fieldPath?: string | null
  /** Canvas validation rule id when the finding came from frontend rules. */
  rule?: string | null
}

// Builder state interface
export type BuilderState = {
  confirmDialogOpen: boolean
  deleteDialogOpen: boolean
  unsavedStepEditorDialogOpen: boolean
  detailsOpen: boolean
  historyCardOpen: boolean
  versionHistoryOpen: boolean
  viewingVersion: number | null
  isKebabOpen: boolean
  addNodePanelOpen: boolean
  nodeEditorMode: 'add' | 'edit' | null
  nodeEditorNodeTypeId: string | null
  nodeEditorNodeSubtypeId: string | null
  selectedNode: Node<NodeType['data']> | null
  sourceNodeId: string | null
  targetNodeId: string | null
  edgeIdToReplace: string | null
  sourceHandle: string | undefined
  targetHandle: string | undefined
  replacementNodeId: string | null
  newNodeDesiredPosition: FlowPosition | null
  mostRecentExecutionId: string | null
  /** Activity IDs from a copied run; skip inference is limited to this allowlist when set. */
  copiedRunActivityIds: ReadonlySet<string> | null
  mostRecentRunPanelOpen: boolean
  selectedTriggerIndex: number
  workflowName: string
  workflowDescription: string
  validationErrors: ValidationError[]
  validationBannerDismissed: boolean
  validationSource: ValidationSource | null
}

// Builder action types
export type BuilderAction =
  | { type: 'SET_CONFIRM_DIALOG'; payload: boolean }
  | { type: 'SET_DELETE_DIALOG'; payload: boolean }
  | { type: 'SET_UNSAVED_STEP_EDITOR_DIALOG'; payload: boolean }
  | { type: 'SET_DETAILS_OPEN'; payload: boolean }
  | { type: 'TOGGLE_DETAILS' }
  | { type: 'SET_HISTORY_CARD_OPEN'; payload: boolean }
  | { type: 'TOGGLE_HISTORY' }
  | { type: 'SET_VERSION_HISTORY_OPEN'; payload: boolean }
  | { type: 'TOGGLE_VERSION_HISTORY' }
  | { type: 'SET_VIEWING_VERSION'; payload: number | null }
  | { type: 'EXIT_VERSION_VIEW' }
  | { type: 'SET_KEBAB_OPEN'; payload: boolean }
  | { type: 'SET_ADD_NODE_PANEL'; payload: boolean }
  | { type: 'OPEN_NODE_EDITOR_ADD'; payload: { nodeTypeId: string; nodeSubtypeId: string | null } }
  | { type: 'CLOSE_NODE_EDITOR' }
  | { type: 'SET_SELECTED_NODE'; payload: Node<NodeType['data']> | null }
  | { type: 'SET_SOURCE_NODE_ID'; payload: string | null }
  | { type: 'SET_TARGET_NODE_ID'; payload: string | null }
  | { type: 'SET_EDGE_ID_TO_REPLACE'; payload: string | null }
  | { type: 'SET_SOURCE_HANDLE'; payload: string | undefined }
  | { type: 'SET_TARGET_HANDLE'; payload: string | undefined }
  | { type: 'SET_REPLACEMENT_NODE_ID'; payload: string | null }
  | { type: 'SET_WORKFLOW_NAME'; payload: string }
  | { type: 'SET_WORKFLOW_DESCRIPTION'; payload: string }
  | {
      type: 'OPEN_ADD_NODE_FROM_EDGE'
      payload: {
        sourceId: string
        targetId?: string
        edgeId?: string
        handle?: string
        targetHandle?: string
        desiredPosition?: FlowPosition
      }
    }
  | { type: 'CLEAR_NEW_NODE_DESIRED_POSITION' }
  | { type: 'SET_NEW_NODE_DESIRED_POSITION'; payload: FlowPosition }
  | {
      type: 'OPEN_ADD_NODE_PANEL'
      payload: { sourceNodeId: string | null; replacementNodeId: string | null; sourceHandle?: string }
    }
  | { type: 'CLOSE_ADD_NODE_PANEL' }
  | { type: 'CLOSE_OTHER_PANELS' }
  | { type: 'NODE_CLICK'; payload: { node: Node<NodeType['data']>; isGeneric: boolean } }
  | { type: 'CLEAR_SELECTED_IF_DELETED'; payload: string[] }
  | {
      type: 'SET_MOST_RECENT_EXECUTION'
      payload: { executionId: string; copiedRunActivityIds?: readonly string[] }
    }
  | { type: 'CLOSE_MOST_RECENT_RUN_PANEL' }
  | { type: 'SET_SELECTED_TRIGGER'; payload: number }
  | {
      type: 'INIT_WORKFLOW'
      payload: { name: string; description: string; initialViewVersion?: number | null }
    }
  | { type: 'SET_VALIDATION_ERRORS'; payload: ValidationError[]; source?: ValidationSource }
  | { type: 'CLEAR_VALIDATION_ERRORS' }
  | { type: 'CLEAR_NODE_VALIDATION_ERRORS'; payload: { nodeId: string } }
  | { type: 'DISMISS_VALIDATION_BANNER' }

// Reducer function
export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  // Route to appropriate handler based on action type category
  if (SIMPLE_ACTIONS.includes(action.type as (typeof SIMPLE_ACTIONS)[number])) {
    return handleSimpleStateUpdate(state, action as Extract<BuilderAction, { type: (typeof SIMPLE_ACTIONS)[number] }>)
  }

  if (PANEL_ACTIONS.includes(action.type as (typeof PANEL_ACTIONS)[number])) {
    return handlePanelActions(state, action)
  }

  const validationResult = handleValidationAction(state, action)
  if (validationResult) return validationResult

  // Remaining complex actions
  // Exhaustiveness checked in helper functions; switch only handles unrouted actions
  // eslint-disable-next-line @typescript-eslint/switch-exhaustiveness-check
  switch (action.type) {
    case 'TOGGLE_DETAILS': {
      const panelIsOpening = !state.detailsOpen
      return panelIsOpening
        ? {
            ...state,
            detailsOpen: true,
            historyCardOpen: false,
            versionHistoryOpen: false,
            addNodePanelOpen: false,
            ...clearEditorAndOtherPanels(),
          }
        : {
            ...state,
            detailsOpen: false,
          }
    }
    case 'TOGGLE_HISTORY': {
      const panelIsOpening = !state.historyCardOpen
      return panelIsOpening
        ? {
            ...state,
            historyCardOpen: true,
            detailsOpen: false,
            versionHistoryOpen: false,
            addNodePanelOpen: false,
            ...clearEditorAndOtherPanels(),
          }
        : {
            ...state,
            historyCardOpen: false,
          }
    }
    case 'TOGGLE_VERSION_HISTORY': {
      const panelIsOpening = !state.versionHistoryOpen
      return panelIsOpening
        ? {
            ...state,
            versionHistoryOpen: true,
            detailsOpen: false,
            historyCardOpen: false,
            addNodePanelOpen: false,
            ...clearEditorAndOtherPanels(),
          }
        : {
            ...state,
            versionHistoryOpen: false,
          }
    }
    case 'EXIT_VERSION_VIEW':
      return { ...state, viewingVersion: null }
    case 'NODE_CLICK':
      return handleNodeClick(state, action)
    case 'CLEAR_SELECTED_IF_DELETED':
      if (state.selectedNode && action.payload.includes(state.selectedNode.id)) {
        return {
          ...state,
          selectedNode: null,
          nodeEditorMode: null,
          nodeEditorNodeTypeId: null,
          nodeEditorNodeSubtypeId: null,
        }
      }
      return state
    case 'SET_MOST_RECENT_EXECUTION':
      return {
        ...state,
        mostRecentExecutionId: action.payload.executionId,
        mostRecentRunPanelOpen: true,
        // Restrict skip inference only when copy-to-editor provides an allowlist
        copiedRunActivityIds: action.payload.copiedRunActivityIds ? new Set(action.payload.copiedRunActivityIds) : null,
      }
    case 'CLOSE_MOST_RECENT_RUN_PANEL':
      return {
        ...state,
        mostRecentRunPanelOpen: false,
      }
    case 'INIT_WORKFLOW':
      // SECURITY: Reset all UI state when initializing a new workflow
      // Prevents stale UI state (selected nodes, open panels) from persisting across workflow changes
      return {
        ...state,
        // Reset workflow metadata
        workflowName: action.payload.name,
        workflowDescription: action.payload.description,
        // Reset UI state to prevent stale selections/panels from previous workflow
        selectedNode: null,
        nodeEditorMode: null,
        nodeEditorNodeTypeId: null,
        nodeEditorNodeSubtypeId: null,
        addNodePanelOpen: false,
        detailsOpen: false,
        historyCardOpen: false,
        versionHistoryOpen: action.payload.initialViewVersion != null,
        viewingVersion: action.payload.initialViewVersion ?? null,
        selectedTriggerIndex: 0,
        mostRecentExecutionId: null,
        copiedRunActivityIds: null,
        mostRecentRunPanelOpen: false,
        validationErrors: [],
        validationBannerDismissed: false,
        validationSource: null,
        // Reset edge connection context
        sourceNodeId: null,
        targetNodeId: null,
        edgeIdToReplace: null,
        sourceHandle: undefined,
        targetHandle: undefined,
        replacementNodeId: null,
        newNodeDesiredPosition: null,
      }
    default:
      return state
  }
}

// Initial state factory
export function getInitialBuilderState(): BuilderState {
  return {
    confirmDialogOpen: false,
    deleteDialogOpen: false,
    unsavedStepEditorDialogOpen: false,
    detailsOpen: false,
    historyCardOpen: false,
    versionHistoryOpen: false,
    viewingVersion: null,
    isKebabOpen: false,
    addNodePanelOpen: false,
    nodeEditorMode: null,
    nodeEditorNodeTypeId: null,
    nodeEditorNodeSubtypeId: null,
    selectedNode: null,
    sourceNodeId: null,
    targetNodeId: null,
    edgeIdToReplace: null,
    sourceHandle: undefined,
    targetHandle: undefined,
    replacementNodeId: null,
    newNodeDesiredPosition: null,
    mostRecentExecutionId: null,
    copiedRunActivityIds: null,
    mostRecentRunPanelOpen: false,
    selectedTriggerIndex: 0,
    workflowName: '',
    workflowDescription: '',
    validationErrors: [],
    validationBannerDismissed: false,
    validationSource: null,
  }
}
