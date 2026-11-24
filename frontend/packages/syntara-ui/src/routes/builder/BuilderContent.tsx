import { StackItem } from '@patternfly/react-core'
import { useState } from 'react'

import { SynLabel } from '../../components/labels/SynLabel'
import { SynPage } from '../../components/layout/SynPage'
import { SynReactFlowViewportGuard } from '../../components/layout/SynReactFlowViewportGuard'
import { SynStepExpandedAllContext } from '../../components/steps/SynStepExpandedAllContext'
import { useFeatureFlag } from '../../providers/use-feature-flag'
import { detachPromise } from '../../utils/detachPromise'

import { useBuilderAuthoring } from './builderAuthoring'
import { useBuilderDuplication } from './builderDuplication'
import { BuilderReadOnlyBanner } from './BuilderReadOnlyBanner'
import { useBuilderSession } from './builderSession'
import { BuilderWorkflowPageHeader } from './BuilderWorkflowPageHeader'
import { BuilderWorkspace } from './BuilderWorkspace'
import { useBuilderWorkspace } from './builderWorkspaceState'
import { BuilderDialogs } from './components/BuilderDialogs'
import { UnsavedStepEditorDialog } from './components/UnsavedStepEditorDialog'
import { useBuilderDialogProps } from './hooks/useBuilderDialogProps'
import { useBuilderVersionPanel } from './hooks/useBuilderVersionPanel'
import { SaveBeforeViewDialog } from './SaveBeforeViewDialog'
import { StepActionsContext } from './StepActionsContext'
import type { BuilderContentProps } from './types/builderContent'
import type { PendingImportData } from './useWorkflowImportExport'
import { ValidationBanner } from './ValidationBanner'
import { StepFormReadOnlyContext } from './VersionViewContext'
import { VersionViewProvider } from './VersionViewProvider'

export function BuilderContent(props: BuilderContentProps) {
  const { workflow, isNew, workflowId } = props
  const isWorkflowBuilderQolEnabled = useFeatureFlag('workflow_builder_qol')
  const session = useBuilderSession(props)
  const { state, dispatch, builderPermissions, isBuiltin, setLocation } = session
  const { currentWorkflow, markDirty, isDirty } = session.store
  const { workflowName, workflowDescription } = state
  const authoring = useBuilderAuthoring(props, session)
  const workspace = useBuilderWorkspace(session, authoring.guardedSaveWorkflow)
  const duplication = useBuilderDuplication({
    workflow,
    workflowName,
    workflowDescription,
    currentWorkflow,
    setLocation,
    canCreate: builderPermissions.canCreate,
    guardedSaveWorkflow: authoring.guardedSaveWorkflow,
  })
  const [pendingImport, setPendingImport] = useState<PendingImportData | null>(null)
  const versionPanel = useBuilderVersionPanel({
    workflowId,
    isNew,
    workflow,
    viewingVersion: state.viewingVersion,
    versionHistoryOpen: state.versionHistoryOpen,
    dispatch,
    handleSaveWorkflow: authoring.handleSaveWorkflow,
    expandAllEvent: session.expandAllEvents.expandAllEvent,
    baseHandleToggleVersionHistory: authoring.baseHandleToggleVersionHistory,
    searchParams: session.searchParams,
    setSearchParams: session.setSearchParams,
    onOpenRunHistory: session.handleOpenRunHistory,
    onClearExecutionFilters: session.clearExecutionFilters,
    executedVersionNumbers: session.executionsByVersion,
    onDuplicateVersion: duplication.onDuplicateVersion,
    onVersionUpdated: authoring.onVersionUpdated,
    canEdit: builderPermissions.canEdit,
    canCreate: builderPermissions.canCreate,
    saveTooltip: builderPermissions.tooltips.save,
  })
  const dialogProps = useBuilderDialogProps({
    workflowName,
    workflowId,
    confirmDialogOpen: state.confirmDialogOpen && !authoring.runDialogBecameStale,
    deleteDialogOpen: state.deleteDialogOpen,
    selectedTriggerId: state.runSelection?.triggerId,
    currentWorkflow,
    runWorkflow: authoring.runWorkflow,
    runReadOnly: authoring.isReadOnly,
    dispatch,
    handleRunWorkflow: authoring.handleRunWorkflow,
    handleDeleteWorkflow: authoring.handleDeleteWorkflow,
    isDeleting: authoring.isDeleting,
    runStepDialog: workspace.runStepDialog,
    lastRunStepNodeIdRef: workspace.lastRunStepNodeIdRef,
    pendingImport,
    setPendingImport,
    selectedProject: session.stableProjectId ? { id: session.stableProjectId } : null,
    createWorkflow: authoring.createWorkflow,
    setLocation,
    pinnedMockDataForDialog: workspace.pinnedMockDataForDialog,
  })
  return (
    <StepActionsContext.Provider value={workspace.stepActionsValue}>
      <SynStepExpandedAllContext.Provider value={session.expandAllEvents}>
        <StepFormReadOnlyContext.Provider value={!builderPermissions.canEdit && builderPermissions.tooltips.edit}>
          <VersionViewProvider value={versionPanel.isViewingVersion}>
            <SynPage>
              <SynReactFlowViewportGuard>
                <StackItem>
                  <BuilderWorkflowPageHeader
                    workflowName={workflowName}
                    workflowDescription={workflowDescription}
                    isNew={isNew}
                    workflow={workflow?.id ? { id: workflow.id } : undefined}
                    isPending={authoring.isCreating || authoring.isUpdating}
                    isDirty={isDirty}
                    lastSavedAt={workflow?.updated_at}
                    isKebabOpen={state.isKebabOpen}
                    publishedVersionId={workflow?.published_version_id ?? null}
                    currentVersionId={workflow?.version?.id}
                    isPublishing={authoring.isPublishing}
                    ProjectSelector={session.projectDisplay}
                    dispatch={dispatch}
                    markDirty={markDirty}
                    handleToggleHistory={authoring.handleToggleHistory}
                    handleToggleVersionHistory={versionPanel.handleToggleVersionHistory}
                    handleToggleDetails={authoring.handleToggleDetails}
                    handleSaveWorkflow={authoring.guardedSaveWorkflow}
                    onPublish={authoring.onPublish}
                    onUnpublish={authoring.onUnpublish}
                    onDuplicate={duplication.handleDuplicateWorkflow}
                    onPendingImport={setPendingImport}
                    isLiveRunActive={workspace.isLiveRunActive}
                    executionId={state.mostRecentExecutionId}
                    executionStatus={workspace.mostRecentExecution?.status}
                    projectId={session.builderProjectId}
                    onBackToEditor={workspace.isLiveRunActive ? workspace.handleCloseMostRecentRunPanel : undefined}
                    hasApprovalPending={!!workspace.pendingApproval}
                    isApprovalLoading={workspace.isApprovalLoading}
                    isApprovalPanelOpen={workspace.approvalViewOpen}
                    onReviewApproval={workspace.openApprovalView}
                    triggers={authoring.runWorkflow?.triggers}
                    isAddStepPanelOpen={session.isAddStepPanelOpen}
                    hasNoWorkflowSteps={session.hasNoWorkflowSteps}
                    isBuiltin={isBuiltin}
                    builderPermissions={builderPermissions}
                    isViewingVersion={versionPanel.isViewingVersion}
                    versionHistoryOpen={state.versionHistoryOpen}
                    viewedVersionDate={versionPanel.viewedVersionDate}
                    viewedVersionStatus={versionPanel.viewedVersionStatus}
                    onExitVersionView={versionPanel.handleExitVersionView}
                    onRestoreVersion={versionPanel.openRestoreDialogForCurrentVersion}
                    isRestoreDisabled={!versionPanel.canRestoreSelectedVersion}
                    restoreTooltip={versionPanel.restoreTooltip}
                    isStepEditorOpen={session.isStepEditorOpen}
                  />
                </StackItem>
                {isWorkflowBuilderQolEnabled && (
                  <StackItem>
                    <SynLabel status="info">workflow_builder_qol is enabled (test proof of concept)</SynLabel>
                  </StackItem>
                )}
                <BuilderPermissionBanner
                  session={session}
                  versionPanel={versionPanel}
                  runUsesSavedVersion={authoring.runUsesSavedVersion}
                />
                <ValidationBanner
                  errors={state.validationErrors}
                  dismissed={state.validationBannerDismissed}
                  source={state.validationSource ?? 'verify'}
                  dispatch={dispatch}
                  onNavigateToStep={workspace.handleNavigateToStep}
                />
                <BuilderWorkspace
                  workflow={workflow}
                  workflowId={workflowId}
                  isNew={isNew}
                  session={session}
                  workspace={workspace}
                  versionPanel={versionPanel}
                  autoSubmitRef={authoring.autoSubmitRef}
                />
              </SynReactFlowViewportGuard>
              <BuilderDialogs {...dialogProps} conflictDialogProps={authoring.conflictDialogProps} />
              <UnsavedStepEditorDialog
                isOpen={state.unsavedStepEditorDialogOpen}
                onClose={() => dispatch({ type: 'SET_UNSAVED_STEP_EDITOR_DIALOG', payload: false })}
              />
              <SaveBeforeViewDialog
                {...duplication.navigationDialog}
                title="Save changes before opening the duplicated workflow?"
                bodyText="Opening the duplicated workflow will exit the editor view and will permanently delete all recent unsaved progress on your current workflow. Please save your work before leaving."
                buttonLabel="Open without saving"
              />
            </SynPage>
          </VersionViewProvider>
        </StepFormReadOnlyContext.Provider>
      </SynStepExpandedAllContext.Provider>
    </StepActionsContext.Provider>
  )
}

function BuilderPermissionBanner({
  session,
  versionPanel,
  runUsesSavedVersion,
}: {
  session: ReturnType<typeof useBuilderSession>
  versionPanel: ReturnType<typeof useBuilderVersionPanel>
  runUsesSavedVersion: boolean
}) {
  const { builderPermissions, stepTypePermissions, isBuiltin } = session
  return (
    <BuilderReadOnlyBanner
      canEdit={builderPermissions.canEdit}
      isLoading={builderPermissions.isLoading || versionPanel.selectedVersionPermissionLoading}
      isBuiltin={isBuiltin}
      runUsesSavedVersion={runUsesSavedVersion}
      blockedStepTypes={stepTypePermissions.blockedStepTypes}
      permissionCheckError={stepTypePermissions.isError || versionPanel.selectedVersionPermissionError}
      onRetryPermissionCheck={() =>
        detachPromise(Promise.all([stepTypePermissions.retry(), versionPanel.retrySelectedVersionPermissions()]))
      }
    />
  )
}
