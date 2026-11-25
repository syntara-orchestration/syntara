import { useCallback, useMemo } from 'react'

import type { useBuilderSession } from './builderSession'
import { useBuilderApproval } from './hooks/useBuilderApproval'
import { useBuilderFlowInteractionHandlers } from './hooks/useBuilderFlowInteractionHandlers'
import { useBuilderLiveRunPanel } from './hooks/useBuilderLiveRunPanel'
import { useBuilderWindowEffects } from './hooks/useBuilderWindowEffects'
import { useRunStepDialog } from './hooks/useRunStepDialog'
import { useStepPanelNavigation } from './hooks/useStepPanelNavigation'
import { useStepTypeCanvasGuards } from './stepTypeCanvasGuards'
import { createAddStepHandler } from './utils/panelActions'

type Session = ReturnType<typeof useBuilderSession>

export function useBuilderWorkspace(session: Session, guardedSaveWorkflow: () => Promise<boolean>) {
  const {
    dispatch,
    reactFlowInstance,
    isStepEditorOpen,
    builderPermissions,
    nodesInitialized,
    mostRecentExecutionQuery,
  } = session
  const { currentWorkflow } = session.store
  const clearDesiredPosition = useCallback(() => dispatch({ type: 'CLEAR_NEW_NODE_DESIRED_POSITION' }), [dispatch])
  // Refuse duplicating or pasting a step type the caller may not author in
  // this project, with the add-step panel's message (UX only; the server
  // still rejects the save).
  const { duplicateActivity, getImportRefusal } = useStepTypeCanvasGuards({
    projectId: session.builderProjectId,
    currentWorkflow,
    duplicateActivity: session.store.duplicateActivity,
    onDuplicateRefused: clearDesiredPosition,
  })
  const { mostRecentExecutionId, mostRecentRunPanelOpen, edgeIdToReplace, targetNodeId, sourceHandle, targetHandle } =
    session.state
  const mostRecentExecution = mostRecentExecutionQuery.data
  const {
    showMostRecentRunPanelInEditor,
    isTerminalStatus,
    isLiveRunActive,
    canvasExecutionStatus,
    mostRecentSelectedNodeId,
    mostRecentSelectedNodeName,
    mostRecentPanelHeight,
    handleMostRecentResize,
    handleMostRecentNodeSelect,
    handleCloseMostRecentRunPanel,
    isPanelExpanded,
    panelExpandControl,
  } = useBuilderLiveRunPanel({
    mostRecentExecutionId,
    mostRecentRunPanelOpen,
    executionStatus: mostRecentExecution?.status,
    isViewingExecution: false,
    onClosePanel: () => dispatch({ type: 'CLOSE_MOST_RECENT_RUN_PANEL' }),
  })

  const { runStepDialog, lastRunStepNodeIdRef, pinnedMockDataForDialog, handleRunStep, suppressPanelCloseRef } =
    useRunStepDialog(guardedSaveWorkflow, isTerminalStatus, isStepEditorOpen)
  const handleCloseStepEditor = useCallback(() => {
    if (suppressPanelCloseRef.current) return
    dispatch({ type: 'CLOSE_NODE_EDITOR' })
  }, [dispatch, suppressPanelCloseRef])
  const {
    handleNodeClick,
    handleClearDesiredPosition,
    handleAddNodeFromEdge,
    handleConnectFromPanel,
    handleNodesDeleted,
    stepActionsValue,
  } = useBuilderFlowInteractionHandlers({
    reactFlowInstance,
    dispatch,
    duplicateActivity,
    edgeIdToReplace,
    targetNodeId,
    sourceHandle,
    targetHandle,
    onRunStep: handleRunStep,
    canEdit: builderPermissions.canEdit,
  })
  const handleNavigateToStep = useStepPanelNavigation(reactFlowInstance, dispatch)
  const handleAddStepFromPanel = useMemo(
    () => createAddStepHandler(dispatch, builderPermissions.canEdit),
    [dispatch, builderPermissions.canEdit]
  )
  useBuilderWindowEffects(nodesInitialized, reactFlowInstance)
  const {
    pendingApproval,
    isApprovalLoading,
    approvalViewOpen,
    approvalMessage,
    wrappedHandleNodeClick,
    handleApprovalClose,
    handleApprovalDismiss,
    openApprovalView,
  } = useBuilderApproval({
    mostRecentExecutionId,
    showMostRecentRunPanelInEditor,
    currentWorkflow,
    handleNodeClick,
    isLiveRunActive,
  })
  return {
    mostRecentExecution,
    showMostRecentRunPanelInEditor,
    showCanvas: !(showMostRecentRunPanelInEditor && isPanelExpanded),
    isLiveRunActive,
    canvasExecutionStatus,
    mostRecentSelectedNodeId,
    mostRecentSelectedNodeName,
    mostRecentPanelHeight,
    handleMostRecentResize,
    handleMostRecentNodeSelect,
    handleCloseMostRecentRunPanel,
    isPanelExpanded,
    panelExpandControl,
    isTerminalStatus,
    runStepDialog,
    lastRunStepNodeIdRef,
    pinnedMockDataForDialog,
    handleRunStep,
    handleCloseStepEditor,
    handleClearDesiredPosition,
    handleAddNodeFromEdge,
    handleConnectFromPanel,
    handleNodesDeleted,
    stepActionsValue,
    getImportRefusal,
    handleNavigateToStep,
    handleAddStepFromPanel,
    pendingApproval,
    isApprovalLoading,
    approvalViewOpen,
    approvalMessage,
    wrappedHandleNodeClick,
    handleApprovalClose,
    handleApprovalDismiss,
    openApprovalView,
  }
}
