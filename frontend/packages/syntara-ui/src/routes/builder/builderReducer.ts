import type { Node } from '@xyflow/react'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

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
  | { type: 'DISMISS_VALIDATION_BANNER' }

// Lookup table for simple state updates - maps action type to the state key it updates
type SimpleActionType = (typeof SIMPLE_ACTIONS)[number]
type SimpleAction = Extract<BuilderAction, { type: SimpleActionType }>

const SIMPLE_STATE_KEY_MAP: Record<
  SimpleActionType,
  keyof Pick<
    BuilderState,
    | 'confirmDialogOpen'
    | 'deleteDialogOpen'
    | 'unsavedStepEditorDialogOpen'
    | 'detailsOpen'
    | 'historyCardOpen'
    | 'versionHistoryOpen'
    | 'viewingVersion'
    | 'isKebabOpen'
    | 'addNodePanelOpen'
    | 'selectedNode'
    | 'sourceNodeId'
    | 'targetNodeId'
    | 'edgeIdToReplace'
    | 'sourceHandle'
    | 'targetHandle'
    | 'replacementNodeId'
    | 'workflowName'
    | 'workflowDescription'
    | 'selectedTriggerIndex'
    | 'validationErrors'
  >
> = {
  SET_CONFIRM_DIALOG: 'confirmDialogOpen',
  SET_DELETE_DIALOG: 'deleteDialogOpen',
  SET_UNSAVED_STEP_EDITOR_DIALOG: 'unsavedStepEditorDialogOpen',
  SET_DETAILS_OPEN: 'detailsOpen',
  SET_HISTORY_CARD_OPEN: 'historyCardOpen',
  SET_VERSION_HISTORY_OPEN: 'versionHistoryOpen',
  SET_VIEWING_VERSION: 'viewingVersion',
  SET_KEBAB_OPEN: 'isKebabOpen',
  SET_ADD_NODE_PANEL: 'addNodePanelOpen',
  SET_SELECTED_NODE: 'selectedNode',
  SET_SOURCE_NODE_ID: 'sourceNodeId',
  SET_TARGET_NODE_ID: 'targetNodeId',
  SET_EDGE_ID_TO_REPLACE: 'edgeIdToReplace',
  SET_SOURCE_HANDLE: 'sourceHandle',
  SET_TARGET_HANDLE: 'targetHandle',
  SET_REPLACEMENT_NODE_ID: 'replacementNodeId',
  SET_WORKFLOW_NAME: 'workflowName',
  SET_WORKFLOW_DESCRIPTION: 'workflowDescription',
  SET_SELECTED_TRIGGER: 'selectedTriggerIndex',
}

/**
 * Helper: Handle simple single-property state updates using a lookup table
 */
function handleSimpleStateUpdate(state: BuilderState, action: SimpleAction): BuilderState {
  const stateKey = SIMPLE_STATE_KEY_MAP[action.type]
  return { ...state, [stateKey]: action.payload }
}

/**
 * Helper: Clear editor state and close other panels when opening a panel
 */
function clearEditorAndOtherPanels(): Partial<BuilderState> {
  return {
    selectedNode: null,
    nodeEditorMode: null,
    nodeEditorNodeTypeId: null,
    nodeEditorNodeSubtypeId: null,
  }
}

/**
 * Helper: Handle panel-related actions (node editor, add node panel)
 *
 * Uses default case to pass through all non-panel actions to the main reducer.
 * The main builderReducer has exhaustiveness checking, so new actions will be caught there.
 */
function handlePanelActions(state: BuilderState, action: BuilderAction): BuilderState {
  // eslint-disable-next-line @typescript-eslint/switch-exhaustiveness-check -- intentional pass-through to main reducer
  switch (action.type) {
    case 'OPEN_NODE_EDITOR_ADD':
      return {
        ...state,
        nodeEditorMode: 'add',
        nodeEditorNodeTypeId: action.payload.nodeTypeId,
        nodeEditorNodeSubtypeId: action.payload.nodeSubtypeId,
        selectedNode: null,
        addNodePanelOpen: false,
      }
    case 'CLOSE_NODE_EDITOR':
      return {
        ...state,
        nodeEditorMode: null,
        nodeEditorNodeTypeId: null,
        nodeEditorNodeSubtypeId: null,
        selectedNode: null,
      }
    case 'OPEN_ADD_NODE_FROM_EDGE':
      return {
        ...state,
        nodeEditorMode: null,
        nodeEditorNodeTypeId: null,
        nodeEditorNodeSubtypeId: null,
        selectedNode: null,
        detailsOpen: false,
        historyCardOpen: false,
        versionHistoryOpen: false,
        sourceNodeId: action.payload.sourceId,
        targetNodeId: action.payload.targetId ?? null,
        edgeIdToReplace: action.payload.edgeId ?? null,
        sourceHandle: action.payload.handle ?? undefined,
        targetHandle: action.payload.targetHandle,
        replacementNodeId: null,
        newNodeDesiredPosition: action.payload.desiredPosition ?? null,
        addNodePanelOpen: true,
      }
    case 'CLEAR_NEW_NODE_DESIRED_POSITION':
      return { ...state, newNodeDesiredPosition: null }
    case 'SET_NEW_NODE_DESIRED_POSITION':
      return { ...state, newNodeDesiredPosition: action.payload }
    case 'OPEN_ADD_NODE_PANEL':
      return {
        ...state,
        nodeEditorMode: null,
        nodeEditorNodeTypeId: null,
        nodeEditorNodeSubtypeId: null,
        selectedNode: null,
        detailsOpen: false,
        historyCardOpen: false,
        versionHistoryOpen: false,
        sourceNodeId: action.payload.sourceNodeId,
        targetNodeId: null,
        edgeIdToReplace: null,
        sourceHandle: action.payload.sourceHandle,
        targetHandle: undefined,
        replacementNodeId: action.payload.replacementNodeId,
        newNodeDesiredPosition: null,
        addNodePanelOpen: true,
      }
    case 'CLOSE_ADD_NODE_PANEL':
      return {
        ...state,
        addNodePanelOpen: false,
        nodeEditorMode: null,
        nodeEditorNodeTypeId: null,
        nodeEditorNodeSubtypeId: null,
        sourceNodeId: null,
        targetNodeId: null,
        edgeIdToReplace: null,
        sourceHandle: undefined,
        targetHandle: undefined,
        replacementNodeId: null,
        newNodeDesiredPosition: null,
      }
    case 'CLOSE_OTHER_PANELS':
      return {
        ...state,
        selectedNode: null,
        detailsOpen: false,
        historyCardOpen: false,
        versionHistoryOpen: false,
      }
    // All other actions are handled by the main reducer
    default:
      return state
  }
}

/**
 * Helper: Handle node click actions
 */
function handleNodeClick(state: BuilderState, action: Extract<BuilderAction, { type: 'NODE_CLICK' }>): BuilderState {
  if (state.viewingVersion !== null) {
    return {
      ...state,
      selectedNode: action.payload.node,
      nodeEditorMode: 'edit',
      nodeEditorNodeTypeId: null,
      nodeEditorNodeSubtypeId: null,
    }
  }
  if (action.payload.isGeneric) {
    return {
      ...state,
      nodeEditorMode: null,
      nodeEditorNodeTypeId: null,
      nodeEditorNodeSubtypeId: null,
      selectedNode: null,
      detailsOpen: false,
      historyCardOpen: false,
      versionHistoryOpen: false,
      sourceNodeId: null,
      replacementNodeId: action.payload.node.id,
      newNodeDesiredPosition: null,
      addNodePanelOpen: true,
      // SECURITY: Clear edge insertion context to prevent mixing replacement mode with edge-insert state
      targetNodeId: null,
      edgeIdToReplace: null,
      sourceHandle: undefined,
      targetHandle: undefined,
    }
  }
  return {
    ...state,
    selectedNode: action.payload.node,
    nodeEditorMode: 'edit',
    nodeEditorNodeTypeId: null,
    nodeEditorNodeSubtypeId: null,
    addNodePanelOpen: false,
    detailsOpen: false,
    historyCardOpen: false,
    versionHistoryOpen: false,
    replacementNodeId: null,
  }
}

// Simple action types that just update a single property
const SIMPLE_ACTIONS = [
  'SET_CONFIRM_DIALOG',
  'SET_DELETE_DIALOG',
  'SET_UNSAVED_STEP_EDITOR_DIALOG',
  'SET_DETAILS_OPEN',
  'SET_HISTORY_CARD_OPEN',
  'SET_VERSION_HISTORY_OPEN',
  'SET_VIEWING_VERSION',
  'SET_KEBAB_OPEN',
  'SET_ADD_NODE_PANEL',
  'SET_SELECTED_NODE',
  'SET_SOURCE_NODE_ID',
  'SET_TARGET_NODE_ID',
  'SET_EDGE_ID_TO_REPLACE',
  'SET_SOURCE_HANDLE',
  'SET_TARGET_HANDLE',
  'SET_REPLACEMENT_NODE_ID',
  'SET_WORKFLOW_NAME',
  'SET_WORKFLOW_DESCRIPTION',
  'SET_SELECTED_TRIGGER',
] as const

// Panel action types
const PANEL_ACTIONS = [
  'OPEN_NODE_EDITOR_ADD',
  'CLOSE_NODE_EDITOR',
  'OPEN_ADD_NODE_FROM_EDGE',
  'CLEAR_NEW_NODE_DESIRED_POSITION',
  'SET_NEW_NODE_DESIRED_POSITION',
  'OPEN_ADD_NODE_PANEL',
  'CLOSE_ADD_NODE_PANEL',
  'CLOSE_OTHER_PANELS',
] as const

function handleValidationAction(state: BuilderState, action: BuilderAction): BuilderState | null {
  if (action.type === 'SET_VALIDATION_ERRORS') {
    return {
      ...state,
      validationErrors: action.payload,
      validationBannerDismissed: false,
      validationSource: action.payload.length === 0 ? null : (action.source ?? 'verify'),
    }
  }
  if (action.type === 'CLEAR_VALIDATION_ERRORS') {
    return { ...state, validationErrors: [], validationBannerDismissed: false, validationSource: null }
  }
  if (action.type === 'DISMISS_VALIDATION_BANNER') {
    return { ...state, validationBannerDismissed: true }
  }
  return null
}

// Reducer function
export function builderReducer(state: BuilderState, action: BuilderAction): BuilderState {
  // Route to appropriate handler based on action type category
  if (SIMPLE_ACTIONS.includes(action.type as (typeof SIMPLE_ACTIONS)[number])) {
    return handleSimpleStateUpdate(state, action as SimpleAction)
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
        return { ...state, selectedNode: null }
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
