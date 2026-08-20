import { AlertActionLink, Flex, FlexItem, Stack, StackItem } from '@patternfly/react-core'
import type { WorkflowAPI } from '@syntara/contracts'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useReactFlow, useNodesInitialized } from '@xyflow/react'
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import { useUnsavedChanges } from '../../app/useUnsavedChanges'
import { executionsClient, workflowClient } from '../../client'
import { SynPage } from '../../components/layout/SynPage'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynReactFlowViewportGuard } from '../../components/layout/SynReactFlowViewportGuard'
import { useSearchParams } from '../../hooks/routing/useSearchParams'
import { useCursorPagination } from '../../hooks/useCursorPagination'
import { useProjectSelector } from '../../hooks/useProjectSelector'
import { useAlerts } from '../../providers/alerts'
import { useWorkflowStore } from '../../stores/useWorkflowStore'
import { getErrorMessage } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { ApprovalSidePanel } from '../executions/ApprovalSidePanel'
import { transformExecutionStatusFilter } from '../executions/executionFilters'
import { NodeExpandedAllContext } from '../workflows/canvas/nodes/common/NodeExpandedAllContext'

import styles from './BuilderContent.module.css'
import { BuilderFlow } from './BuilderFlow'
import { BuilderReadOnlyBanner } from './BuilderReadOnlyBanner'
import { builderReducer, getInitialBuilderState } from './builderReducer'
import { BuilderWorkflowPageHeader } from './BuilderWorkflowPageHeader'
import { BuilderDialogs } from './components/BuilderDialogs'
import { BuilderSidePanels } from './components/BuilderSidePanels'
import { ExecutionDetailsPanelWrapper } from './components/ExecutionDetailsPanelWrapper'
import { NodeEditorOverlay } from './components/NodeEditorOverlay'
import { UnsavedStepEditorDialog } from './components/UnsavedStepEditorDialog'
import { VersionHistorySidePanel } from './components/VersionHistorySidePanel'
import { useBuilderApproval } from './hooks/useBuilderApproval'
import { useBuilderConflict } from './hooks/useBuilderConflict'
import { useBuilderContentQueries } from './hooks/useBuilderContentQueries'
import { useBuilderDerivedUiFlags } from './hooks/useBuilderDerivedUiFlags'
import { useBuilderDialogProps } from './hooks/useBuilderDialogProps'
import { useBuilderFlowInteractionHandlers } from './hooks/useBuilderFlowInteractionHandlers'
import { useBuilderLiveRunPanel } from './hooks/useBuilderLiveRunPanel'
import { useBuilderSaveWorkflow, type UseBuilderSaveWorkflowParams } from './hooks/useBuilderSaveWorkflow'
import { useBuilderToolbarHandlers } from './hooks/useBuilderToolbarHandlers'
import { useBuilderValidation } from './hooks/useBuilderValidation'
import { useBuilderVersionPanel } from './hooks/useBuilderVersionPanel'
import { useBuilderWindowEffects } from './hooks/useBuilderWindowEffects'
import { useBuilderWorkflowLifecycle } from './hooks/useBuilderWorkflowLifecycle'
import { useExecutionCopyToEditor } from './hooks/useExecutionCopyToEditor'
import { useGuardedSaveWorkflow } from './hooks/useGuardedSaveWorkflow'
import { NodeEditorAutoSubmitContext, useNodeEditorAutoSubmitRef } from './hooks/useNodeEditorAutoSubmit'
import { useNodePanelNavigation } from './hooks/useNodePanelNavigation'
import { usePublishWorkflow, useUnpublishWorkflow } from './hooks/usePublishWorkflow'
import { useRunStepDialog } from './hooks/useRunStepDialog'
import { useUndoRedoKeyboard } from './hooks/useUndoRedoKeyboard'
import { useWorkflowMetadata } from './hooks/useWorkflowMetadata'
import { NodeActionsContext } from './NodeActionsContext'
import type { BuilderContentProps } from './types/builderContent'
import { useBuilderPermissions } from './useBuilderPermissions'
import { createAddStepHandler } from './utils/panelActions'
import { ValidationBanner } from './ValidationBanner'
import { VersionInfoCard } from './VersionInfoCard'
import { VersionViewProvider } from './VersionViewContext'

type WorkflowVersion = WorkflowAPI.components['schemas']['WorkflowVersionRead']
/* eslint-disable max-lines */
// eslint-disable-next-line max-lines-per-function, complexity
export function BuilderContent(props: BuilderContentProps) {
  const { workflow, isNew, workflowId, executionCopy, initialViewVersion } = props
  const navigate = useNavigate()
  const setLocation = useCallback(
    (to: string) => {
      detachPromise(navigate({ to }))
    },
    [navigate]
  )
  const [searchParams, setSearchParams] = useSearchParams()
  const { showAlert, showSuccess, showWarning, showError } = useAlerts()
  const [saveAttemptedWithoutProject, setSaveAttemptedWithoutProject] = useState(false)
  const { selectedProject, stableProjectId, ProjectSelector } = useProjectSelector({
    requireProject: isNew,
    initialProjectId: isNew ? undefined : (workflow?.project_id ?? undefined),
    hasValidationError: saveAttemptedWithoutProject,
    onProjectSelect: () => setSaveAttemptedWithoutProject(false),
    isDisabled: !isNew,
    clearSelectionOnMount: isNew,
  })

  const queryClient = useQueryClient()
  const reactFlowInstance = useReactFlow()
  const nodesInitialized = useNodesInitialized()
  const {
    setWorkflow,
    loadWorkflowWithEdges,
    currentWorkflow,
    setEdges: setStoredEdges,
    isDirty,
    markClean,
    markDirty,
    duplicateActivity,
  } = useWorkflowStore()
  const { registerSaveHandler, unregisterSaveHandler, requestNavigation } = useUnsavedChanges()
  const handleExecutionNavigate = useCallback(
    (id: string) => requestNavigation(`/executions/${id}`),
    [requestNavigation]
  )

  const executionExtraParams = useMemo(() => ({ workflow_id: workflowId ?? '' }), [workflowId])
  const {
    filters: executionFilters,
    queryParams: executionsQueryParams,
    handleFilterChange: handleExecutionFilterChange,
    handleClearAllFilters: clearExecutionFilters,
    getFooterProps: getExecutionPaginationFooterProps,
  } = useCursorPagination({
    limit: 20,
    transformFilters: transformExecutionStatusFilter,
    extraParams: executionExtraParams,
    defaultSort: { field: 'created_at', direction: 'desc' as const },
  })
  const [state, dispatch] = useReducer(builderReducer, getInitialBuilderState())
  const autoSubmitRef = useNodeEditorAutoSubmitRef()
  const {
    confirmDialogOpen,
    deleteDialogOpen,
    unsavedStepEditorDialogOpen,
    detailsOpen,
    historyCardOpen,
    isKebabOpen,
    addNodePanelOpen,
    nodeEditorMode,
    nodeEditorNodeTypeId,
    nodeEditorNodeSubtypeId,
    selectedNode,
    sourceNodeId,
    targetNodeId,
    edgeIdToReplace,
    sourceHandle,
    targetHandle,
    replacementNodeId,
    workflowName,
    workflowDescription,
    mostRecentExecutionId,
    copiedRunActivityIds,
    mostRecentRunPanelOpen,
    selectedTriggerIndex,
    viewingVersion,
    versionHistoryOpen,
  } = state

  const [expandAllEvent, collapseAllEvent] = useMemo(() => [new EventTarget(), new EventTarget()], [])
  const { hasNoWorkflowNodes, isAddNodePanelOpen, isNodeEditorOpen } = useBuilderDerivedUiFlags(
    currentWorkflow,
    addNodePanelOpen,
    nodeEditorMode
  )

  useUndoRedoKeyboard({ disabled: isNodeEditorOpen || viewingVersion !== null })
  useEffect(() => () => useWorkflowStore.temporal.getState().clear(), [])
  const { executionsQuery, mostRecentExecutionQuery, workflowsListQuery } = useBuilderContentQueries({
    workflowId,
    isNew,
    executionsQueryParams,
    mostRecentExecutionId,
    mostRecentRunPanelOpen,
  })

  useBuilderWorkflowLifecycle({
    workflowId,
    isNew,
    workflow,
    workflowName,
    initialViewVersion,
    workflowsListResources: workflowsListQuery.data?.resources,
    workflowsListDataUndefined: workflowsListQuery.data === undefined,
    workflowsListIsPending: workflowsListQuery.isPending,
    workflowsListError: workflowsListQuery.error,
    dispatch,
    setWorkflow,
    setStoredEdges,
    loadWorkflowWithEdges,
  })
  useExecutionCopyToEditor({ executionCopy, dispatch, markDirty, showSuccess })

  const initialViewVersionRef = useRef(initialViewVersion)
  useEffect(() => {
    if (initialViewVersionRef.current === initialViewVersion) return
    initialViewVersionRef.current = initialViewVersion
    if (initialViewVersion != null) {
      dispatch({ type: 'SET_VIEWING_VERSION', payload: initialViewVersion })
      dispatch({ type: 'SET_VERSION_HISTORY_OPEN', payload: true })
      dispatch({ type: 'SET_HISTORY_CARD_OPEN', payload: false })
      queueMicrotask(() => {
        clearExecutionFilters()
      })
    }
  }, [initialViewVersion, dispatch, clearExecutionFilters])
  const { handleVerifySilent } = useBuilderValidation({
    dispatch,
  })
  const { mutate: createWorkflow, isPending: isCreating } = workflowClient.useMutation('post', '/workflows')
  const { mutate: updateWorkflow, isPending: isUpdating } = workflowClient.useMutation(
    'patch',
    '/workflows/{workflow_id}'
  )
  const { mutate: executeWorkflow } = executionsClient.useMutation('post', '/executions')
  const { mutate: deleteWorkflow } = workflowClient.useMutation('delete', '/workflows/{workflow_id}')
  const workflowMetadata = useWorkflowMetadata(workflow)
  const currentVersion = workflow?.current_version ?? workflow?.version?.version

  const { loadedVersion, handleConflict, onVersionUpdated, setActions, conflictDialogProps } = useBuilderConflict({
    workflowId,
    workflowName,
    workflowDescription,
    workflowProjectId: workflow?.project_id,
    selectedProjectId: stableProjectId,
    currentWorkflow,
    currentVersion,
    isNew,
    setLocation,
    showError,
    markClean,
  })

  const { unpublish: onUnpublish } = useUnpublishWorkflow(workflowId)
  const handleSaveWorkflow = useBuilderSaveWorkflow({
    currentWorkflow,
    workflowName,
    workflowDescription,
    workflowId,
    isNew,
    selectedProject: stableProjectId ? { id: stableProjectId } : null,
    workflowsListResources: workflowsListQuery.data?.resources,
    queryClient,
    setLocation,
    showSuccess,
    showWarning,
    showError,
    onMissingProjectForCreate: () => setSaveAttemptedWithoutProject(true),
    markClean,
    expectedVersion: loadedVersion,
    onConflict: handleConflict('save'),
    onVersionUpdated,
    onSaveWithValidationIssues: handleVerifySilent,
    onValidationFindings: (errors) => {
      if (errors.length === 0) {
        dispatch({ type: 'CLEAR_VALIDATION_ERRORS' })
        useWorkflowStore.getState().setValidationErrorCount(0)
        return
      }
      dispatch({ type: 'SET_VALIDATION_ERRORS', payload: errors, source: 'save' })
      useWorkflowStore.getState().setValidationErrorCount(errors.length)
    },
    createWorkflow: createWorkflow as UseBuilderSaveWorkflowParams['createWorkflow'],
    updateWorkflow,
  })
  const guardedSaveWorkflow = useGuardedSaveWorkflow(
    handleSaveWorkflow,
    isNodeEditorOpen,
    nodeEditorMode,
    autoSubmitRef,
    dispatch
  )

  const { publish: onPublish, isPublishing } = usePublishWorkflow(
    workflowId,
    currentVersion,
    workflowName,
    workflowDescription,
    { expectedVersion: loadedVersion, onConflict: handleConflict('publish'), onVersionUpdated }
  )

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
  } = useBuilderLiveRunPanel({
    mostRecentExecutionId,
    mostRecentRunPanelOpen,
    executionStatus: mostRecentExecution?.status,
    isViewingExecution: false,
    onClosePanel: () => dispatch({ type: 'CLOSE_MOST_RECENT_RUN_PANEL' }),
  })

  const { runStepDialog, lastRunStepNodeIdRef, pinnedMockDataForDialog, handleRunStep, suppressPanelCloseRef } =
    useRunStepDialog(handleSaveWorkflow, isTerminalStatus)
  const handleCloseNodeEditor = useCallback(() => {
    if (suppressPanelCloseRef.current) return
    dispatch({ type: 'CLOSE_NODE_EDITOR' })
  }, [dispatch, suppressPanelCloseRef])
  const [pendingImport, setPendingImport] = useState<import('./useWorkflowImportExport').PendingImportData | null>(null)
  const {
    handleRunWorkflow,
    handleDeleteWorkflow,
    handleToggleDetails,
    handleToggleHistory,
    handleToggleVersionHistory: baseHandleToggleVersionHistory,
  } = useBuilderToolbarHandlers({
    workflow: workflow as { id: string } | undefined,
    workflowName,
    detailsOpen,
    historyCardOpen,
    reactFlowInstance,
    executionsQuery,
    dispatch,
    executeWorkflow,
    deleteWorkflow,
    showSuccess,
    showError,
    setLocation,
    handleSaveWorkflow: guardedSaveWorkflow,
    currentWorkflow,
    loadedVersion,
    loadedVersionName: workflow?.version?.name ?? null,
    loadedVersionCreatedAt: workflow?.version?.created_at ?? null,
    onRunConflict: handleConflict('run'),
  })
  useEffect(() => {
    registerSaveHandler(handleSaveWorkflow)
    setActions({ handleSaveWorkflow, onPublish, handleRunWorkflow })
    return () => unregisterSaveHandler()
  }, [handleSaveWorkflow, onPublish, handleRunWorkflow, registerSaveHandler, unregisterSaveHandler, setActions])

  const executionsByVersion = useMemo(() => {
    const map = new Map<number, string>()
    for (const e of executionsQuery.data?.resources ?? []) {
      const versionNum = e.workflow_version
      const versionId = e.workflow_version_id
      if (versionNum != null && versionId && !map.has(versionNum)) {
        map.set(versionNum, versionId)
      }
    }
    return map
  }, [executionsQuery.data?.resources])

  const executionPaginationFooterProps = useMemo(
    () => getExecutionPaginationFooterProps(executionsQuery.data),
    [getExecutionPaginationFooterProps, executionsQuery.data]
  )

  const handleOpenRunHistory = useCallback(
    (versionNumber: number) => {
      const versionId = executionsByVersion.get(versionNumber)
      if (versionId) {
        handleExecutionFilterChange([{ key: 'workflow_version_id', value: versionId, operator: 'eq' }])
      }
      dispatch({ type: 'SET_HISTORY_CARD_OPEN', payload: true })
    },
    [dispatch, executionsByVersion, handleExecutionFilterChange]
  )

  const { mutate: duplicateWorkflow, isPending: isDuplicating } = workflowClient.useMutation('post', '/workflows')
  const handleDuplicateVersion = useCallback(
    (version: WorkflowVersion) => {
      if (isDuplicating || !workflow?.name || !workflow.project_id) return
      const definition = version.workflow_definition
      if (!definition) {
        showError({ title: 'Failed to duplicate workflow', description: 'Version has no definition to duplicate' })
        return
      }
      const timestamp = Date.now().toString(36)
      const suffix = ` - duplicate-${timestamp}`
      const maxBaseLength = 255 - suffix.length
      const baseName = workflow.name.length > maxBaseLength ? workflow.name.slice(0, maxBaseLength) : workflow.name
      const duplicateName = `${baseName}${suffix}`
      duplicateWorkflow(
        {
          body: {
            name: duplicateName,
            description: workflow.description ?? '',
            workflow_definition: definition,
            labels: workflow.labels ?? {},
            project_id: workflow.project_id,
          },
        },
        {
          onSuccess: (created) => {
            showAlert({
              variant: 'success',
              autoDismiss: true,
              title: 'Workflow duplicated',
              description: `Created "${duplicateName}"`,
              actionLinks: created?.id ? (
                <AlertActionLink onClick={() => setLocation(`/workflow-builder/${created.id}`)}>
                  Open workflow
                </AlertActionLink>
              ) : undefined,
            })
            detachPromise(
              queryClient.invalidateQueries({
                predicate: (q) =>
                  q.queryKey[0] === 'get' &&
                  typeof q.queryKey[1] === 'string' &&
                  q.queryKey[1].startsWith('/workflows'),
              })
            )
          },
          onError: (error: unknown) => {
            showError({ title: 'Failed to duplicate workflow', description: getErrorMessage(error) })
          },
        }
      )
    },
    [isDuplicating, workflow, duplicateWorkflow, queryClient, showAlert, showError, setLocation]
  )

  const versionPanel = useBuilderVersionPanel({
    workflowId,
    isNew,
    workflow,
    viewingVersion,
    versionHistoryOpen,
    dispatch,
    handleSaveWorkflow,
    workflowName,
    expandAllEvent,
    baseHandleToggleVersionHistory,
    searchParams,
    setSearchParams,
    onOpenRunHistory: handleOpenRunHistory,
    onClearExecutionFilters: clearExecutionFilters,
    executedVersionNumbers: executionsByVersion,
    onDuplicateVersion: (v: WorkflowVersion) => detachPromise(handleDuplicateVersion(v)),
    onVersionUpdated,
  })

  const {
    handleNodeClick,
    handleClearDesiredPosition,
    handleAddNodeFromEdge,
    handleConnectFromPanel,
    handleNodesDeleted,
    nodeActionsValue,
  } = useBuilderFlowInteractionHandlers({
    reactFlowInstance,
    dispatch,
    duplicateActivity,
    edgeIdToReplace,
    targetNodeId,
    sourceHandle,
    targetHandle,
    onRunStep: handleRunStep,
  })
  const handleNavigateToNode = useNodePanelNavigation(reactFlowInstance, dispatch)
  const handleAddStepFromPanel = useMemo(() => createAddStepHandler(dispatch), [dispatch])
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
  // UUID only — NodeDetailsPanel / CredentialSelector / integrations filter by project_id.
  // can_i also accepts UUID (backend resolves to project name).
  const builderProjectId = workflow?.project_id ?? selectedProject?.id ?? stableProjectId
  const builderPermissions = useBuilderPermissions(isNew, currentWorkflow?.is_builtin === true, builderProjectId)
  const triggers = currentWorkflow?.triggers ?? []
  const nodeExpandedAllContextValue = useMemo(
    () => ({ expandAllEvent, collapseAllEvent }),
    [expandAllEvent, collapseAllEvent]
  )
  const dialogProps = useBuilderDialogProps({
    workflowName,
    workflowId,
    confirmDialogOpen,
    deleteDialogOpen,
    selectedTriggerIndex,
    currentWorkflow,
    dispatch,
    handleRunWorkflow,
    handleDeleteWorkflow,
    runStepDialog,
    lastRunStepNodeIdRef,
    pendingImport,
    setPendingImport,
    selectedProject: stableProjectId ? { id: stableProjectId } : null,
    createWorkflow: createWorkflow as UseBuilderSaveWorkflowParams['createWorkflow'],
    setLocation,
    pinnedMockDataForDialog,
  })
  return (
    <NodeActionsContext.Provider value={nodeActionsValue}>
      <NodeExpandedAllContext.Provider value={nodeExpandedAllContextValue}>
        <VersionViewProvider value={versionPanel.isViewingVersion}>
          <SynPage>
            <SynReactFlowViewportGuard>
              <Stack hasGutter>
                <StackItem>
                  <BuilderWorkflowPageHeader
                    workflowName={workflowName}
                    workflowDescription={workflowDescription}
                    isNew={isNew}
                    workflow={workflow?.id ? { id: workflow.id } : undefined}
                    isPending={isCreating || isUpdating}
                    isDirty={isDirty}
                    lastSavedAt={workflow?.updated_at}
                    isKebabOpen={isKebabOpen}
                    publishedVersionId={workflow?.published_version_id ?? null}
                    currentVersionId={workflow?.version?.id}
                    isPublishing={isPublishing}
                    ProjectSelector={ProjectSelector}
                    dispatch={dispatch}
                    markDirty={markDirty}
                    handleToggleHistory={handleToggleHistory}
                    handleToggleVersionHistory={versionPanel.handleToggleVersionHistory}
                    handleToggleDetails={handleToggleDetails}
                    handleSaveWorkflow={guardedSaveWorkflow}
                    onPublish={onPublish}
                    onUnpublish={onUnpublish}
                    onPendingImport={setPendingImport}
                    isLiveRunActive={isLiveRunActive}
                    executionId={mostRecentExecutionId}
                    executionStatus={mostRecentExecution?.status}
                    onBackToEditor={isLiveRunActive ? handleCloseMostRecentRunPanel : undefined}
                    hasApprovalPending={!!pendingApproval}
                    isApprovalLoading={isApprovalLoading}
                    isApprovalPanelOpen={approvalViewOpen}
                    onReviewApproval={openApprovalView}
                    triggers={triggers}
                    isAddNodePanelOpen={isAddNodePanelOpen}
                    hasNoWorkflowNodes={hasNoWorkflowNodes}
                    isBuiltin={currentWorkflow?.is_builtin === true}
                    builderPermissions={builderPermissions}
                    isViewingVersion={versionPanel.isViewingVersion}
                    versionHistoryOpen={versionHistoryOpen}
                    viewedVersionDate={versionPanel.viewedVersionDate}
                    viewedVersionStatus={versionPanel.viewedVersionStatus}
                    onExitVersionView={versionPanel.handleExitVersionView}
                    onRestoreVersion={versionPanel.openRestoreDialogForCurrentVersion}
                    isNodeEditorOpen={isNodeEditorOpen}
                  />
                </StackItem>
                <BuilderReadOnlyBanner
                  canEdit={builderPermissions.canEdit}
                  isLoading={builderPermissions.isLoading}
                  isBuiltin={currentWorkflow?.is_builtin === true}
                />
                <ValidationBanner
                  errors={state.validationErrors}
                  dismissed={state.validationBannerDismissed}
                  source={state.validationSource ?? 'verify'}
                  dispatch={dispatch}
                  onNavigateToNode={handleNavigateToNode}
                />
                <StackItem isFilled className={styles.filledMinHeight}>
                  <Flex
                    alignItems={{ default: 'alignItemsStretch' }}
                    flexWrap={{ default: 'nowrap' }}
                    gap={{ default: 'gapSm' }}
                    className={styles.canvasFlex}
                  >
                    <FlexItem
                      className={styles.canvasFlexItem}
                      style={{ pointerEvents: isNodeEditorOpen && !versionPanel.isViewingVersion ? 'none' : 'auto' }}
                    >
                      <Stack className={styles.canvasStack}>
                        <StackItem isFilled className={styles.filledMinHeight}>
                          <SynPanel hasNoPadding isFullHeight className={styles.canvasPanel}>
                            <VersionInfoCard
                              title={versionPanel.viewedVersionName}
                              date={versionPanel.viewedVersionDate}
                              description={versionPanel.viewedVersionDescription}
                              publishedAt={versionPanel.viewedVersionPublishedAt}
                              unpublishedAt={versionPanel.viewedVersionUnpublishedAt}
                            />
                            <BuilderFlow
                              workflowId={workflowId}
                              readOnly={versionPanel.isViewingVersion}
                              canEdit={builderPermissions.canEdit}
                              panelOpen={isAddNodePanelOpen || !!selectedNode}
                              activeEdgeButtonNodeId={isAddNodePanelOpen ? sourceNodeId : null}
                              activeEdgeButtonHandle={isAddNodePanelOpen ? sourceHandle : null}
                              activeEdgeId={isAddNodePanelOpen ? edgeIdToReplace : null}
                              executionStatus={canvasExecutionStatus}
                              copiedRunActivityIds={copiedRunActivityIds}
                              disableDeleteKey={isNodeEditorOpen}
                              disableSpacePanning={isNodeEditorOpen || confirmDialogOpen}
                              onNodeClick={wrappedHandleNodeClick}
                              onAddNodeFromEdge={handleAddNodeFromEdge}
                              onNodesDeleted={handleNodesDeleted}
                              newNodeDesiredPosition={state.newNodeDesiredPosition}
                              onClearDesiredPosition={handleClearDesiredPosition}
                              validationErrors={state.validationErrors}
                            />
                          </SynPanel>
                        </StackItem>
                        {showMostRecentRunPanelInEditor && mostRecentExecutionId && (
                          <ExecutionDetailsPanelWrapper
                            executionId={mostRecentExecutionId}
                            workflowDefinition={
                              workflow?.version?.workflow_definition as Parameters<
                                typeof ExecutionDetailsPanelWrapper
                              >[0]['workflowDefinition']
                            }
                            selectedNodeId={mostRecentSelectedNodeId}
                            selectedNodeName={mostRecentSelectedNodeName}
                            onNodeSelect={handleMostRecentNodeSelect}
                            panelHeight={mostRecentPanelHeight}
                            onResize={handleMostRecentResize}
                            isTerminalStatus={isTerminalStatus}
                            onClosePanel={handleCloseMostRecentRunPanel}
                          />
                        )}
                      </Stack>
                    </FlexItem>
                    <BuilderSidePanels
                      isAddNodePanelOpen={isAddNodePanelOpen}
                      isNodeEditorOpen={isNodeEditorOpen}
                      canEdit={builderPermissions.canEdit}
                      sourceNodeId={sourceNodeId}
                      replacementNodeId={replacementNodeId}
                      hasNoWorkflowNodes={hasNoWorkflowNodes}
                      dispatch={dispatch}
                      historyCardOpen={historyCardOpen}
                      isNew={isNew}
                      executions={executionsQuery.data?.resources ?? []}
                      onExecutionNavigate={handleExecutionNavigate}
                      executionFilters={executionFilters}
                      onFilterChange={handleExecutionFilterChange}
                      executionPaginationFooterProps={executionPaginationFooterProps}
                      detailsOpen={detailsOpen}
                      workflow={workflow}
                      workflowName={workflowName}
                      workflowDescription={workflowDescription}
                      markDirty={markDirty}
                    />

                    {!isNodeEditorOpen && approvalViewOpen && pendingApproval && (
                      <FlexItem className={styles.approvalPanelSlot}>
                        <ApprovalSidePanel
                          approval={pendingApproval}
                          message={approvalMessage}
                          onClose={handleApprovalClose}
                          onDecisionSubmitted={handleApprovalDismiss}
                          onNavigate={setLocation}
                        />
                      </FlexItem>
                    )}

                    <VersionHistorySidePanel
                      sidePanel={versionPanel.versionSidePanel}
                      isNodeEditorOpen={isNodeEditorOpen}
                      editPermission={{
                        canEdit: builderPermissions.canEdit,
                        tooltip: builderPermissions.tooltips.edit,
                      }}
                    />

                    <NodeEditorAutoSubmitContext.Provider value={autoSubmitRef}>
                      <NodeEditorOverlay
                        isOpen={isNodeEditorOpen}
                        mode={nodeEditorMode}
                        selectedNode={selectedNode}
                        nodeTypeId={nodeEditorNodeTypeId}
                        nodeSubtypeId={nodeEditorNodeSubtypeId}
                        sourceNodeId={sourceNodeId}
                        replacementNodeId={replacementNodeId}
                        executionId={mostRecentExecutionId}
                        workflowId={workflowId}
                        onConnect={handleConnectFromPanel}
                        onClose={handleCloseNodeEditor}
                        onNavigateToNode={handleNavigateToNode}
                        onAddStep={handleAddStepFromPanel}
                        projectId={builderProjectId}
                        workflowMetadata={workflowMetadata}
                        onRunStep={selectedNode ? () => detachPromise(handleRunStep(selectedNode.id)) : undefined}
                      />
                    </NodeEditorAutoSubmitContext.Provider>
                  </Flex>
                </StackItem>
              </Stack>
            </SynReactFlowViewportGuard>

            <BuilderDialogs {...dialogProps} conflictDialogProps={conflictDialogProps} />
            <UnsavedStepEditorDialog
              isOpen={unsavedStepEditorDialogOpen}
              onClose={() => dispatch({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: false })}
            />
          </SynPage>
        </VersionViewProvider>
      </NodeExpandedAllContext.Provider>
    </NodeActionsContext.Provider>
  )
}
