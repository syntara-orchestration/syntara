import type { BuilderAction, BuilderState } from './builderReducer'
import { isFormDefinitionValidationFindingForNode } from './utils/validation/formDefinitionValidationFindings'

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

export const SIMPLE_ACTIONS = [
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

export const PANEL_ACTIONS = [
  'OPEN_NODE_EDITOR_ADD',
  'CLOSE_NODE_EDITOR',
  'OPEN_ADD_NODE_FROM_EDGE',
  'CLEAR_NEW_NODE_DESIRED_POSITION',
  'SET_NEW_NODE_DESIRED_POSITION',
  'OPEN_ADD_NODE_PANEL',
  'CLOSE_ADD_NODE_PANEL',
  'CLOSE_OTHER_PANELS',
] as const

export function handleSimpleStateUpdate(state: BuilderState, action: SimpleAction): BuilderState {
  const stateKey = SIMPLE_STATE_KEY_MAP[action.type]
  return { ...state, [stateKey]: action.payload }
}

export function clearEditorAndOtherPanels(): Partial<BuilderState> {
  return {
    selectedNode: null,
    nodeEditorMode: null,
    nodeEditorNodeTypeId: null,
    nodeEditorNodeSubtypeId: null,
  }
}

export function handlePanelActions(state: BuilderState, action: BuilderAction): BuilderState {
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
    default:
      return state
  }
}

export function handleNodeClick(
  state: BuilderState,
  action: Extract<BuilderAction, { type: 'NODE_CLICK' }>
): BuilderState {
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

export function handleValidationAction(state: BuilderState, action: BuilderAction): BuilderState | null {
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
  if (action.type === 'CLEAR_NODE_VALIDATION_ERRORS') {
    const { nodeId } = action.payload
    const filtered = state.validationErrors.filter((error) => !isFormDefinitionValidationFindingForNode(error, nodeId))
    if (filtered.length === state.validationErrors.length) {
      return state
    }
    return {
      ...state,
      validationErrors: filtered,
      validationBannerDismissed: false,
      validationSource: filtered.length === 0 ? null : state.validationSource,
    }
  }
  if (action.type === 'DISMISS_VALIDATION_BANNER') {
    return { ...state, validationBannerDismissed: true }
  }
  return null
}
