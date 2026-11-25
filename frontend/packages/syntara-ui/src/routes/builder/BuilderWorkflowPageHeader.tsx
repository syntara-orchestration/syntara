import { Button, Icon, TitleSizes } from '@patternfly/react-core'
import { RhUiClockIcon, RhUiUndoIcon } from '@patternfly/react-icons'
import type { ExecutionStatus, WorkflowAPI } from '@syntara/contracts'
import { type Dispatch, type ReactNode } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDialogState } from '../../hooks/useDialogState'
import { useDocLink } from '../../utils/docs/useDocLink'
import { CancelExecutionButton } from '../executions/CancelExecutionButton'
import { isExecutionCancellable } from '../executions/executionCancellable'

import { BuilderEditorTitleSlot } from './BuilderEditorTitleSlot'
import { BuilderEditorToolbar } from './BuilderEditorToolbar'
import type { BuilderAction } from './builderReducer'
import { BuilderVersionViewTitleRowAddons } from './BuilderWorkflowPageHeaderParts'
import { builderVersionViewHasTitleRowExtras } from './builderWorkflowPageHeaderTitle'
import { useRemovedSubworkflowTriggerIds } from './hooks/usePublishTriggerRemoval'
import { PublishWorkflowDialog } from './PublishWorkflowDialog'
import type { BuilderPermissions } from './useBuilderPermissions'
import type { PendingImportData } from './useWorkflowImportExport'

type BuilderToolbarContentProps = Readonly<{
  isLiveRunActive?: boolean
  executionId?: string | null
  executionStatus?: ExecutionStatus | null
  projectId?: string
  hasApprovalPending?: boolean
  isApprovalLoading?: boolean
  isApprovalPanelOpen?: boolean
  onBackToEditor?: () => void
  onReviewApproval?: () => void
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  handleToggleHistory: () => void
  handleToggleVersionHistory: () => void
  isNew: boolean
  workflow: { id: string } | undefined
  isPending: boolean
  isDirty: boolean
  lastSavedAt?: string | null
  isKebabOpen: boolean
  publishedVersionId: string | null
  currentVersionId?: string | null
  handleToggleDetails: () => void
  handleSaveWorkflow: () => Promise<boolean>
  onPublishClick: () => void
  onUnpublish: () => void
  onDuplicate: () => void
  onPendingImport: (data: PendingImportData) => void
  triggers?: { id: string; name?: string }[]
  isBuiltin: boolean
  isAddNodePanelOpen: boolean
  hasNoWorkflowNodes: boolean
  workflowName: string
  workflowDescription: string
  builderPermissions: BuilderPermissions
  isViewingVersion?: boolean
  versionHistoryOpen?: boolean
  onExitVersionView?: () => void
  onRestoreVersion?: () => void
  onToggleVersionHistory?: () => void
  isNodeEditorOpen?: boolean
}>

/**
 * Renders appropriate toolbar based on builder state:
 * - Version view active: restore + back to editor + version history toggle
 * - Live run active: optional approval review + back button
 * - Default: full editor toolbar
 */
function BuilderToolbarContent({
  isBuiltin,
  isLiveRunActive,
  executionId,
  executionStatus,
  projectId,
  hasApprovalPending,
  isApprovalLoading,
  isApprovalPanelOpen,
  onBackToEditor,
  onReviewApproval,
  dispatch,
  markDirty,
  handleToggleHistory,
  handleToggleVersionHistory,
  isNew,
  workflow,
  isPending,
  isDirty,
  lastSavedAt,
  isKebabOpen,
  publishedVersionId,
  currentVersionId,
  handleToggleDetails,
  handleSaveWorkflow,
  onPublishClick,
  onUnpublish,
  onDuplicate,
  onPendingImport,
  triggers,
  isAddNodePanelOpen,
  hasNoWorkflowNodes,
  workflowName,
  workflowDescription,
  builderPermissions,
  isViewingVersion,
  versionHistoryOpen,
  onExitVersionView,
  onRestoreVersion,
  onToggleVersionHistory,
  isNodeEditorOpen,
}: BuilderToolbarContentProps) {
  if (isViewingVersion && onExitVersionView) {
    return (
      <>
        {onRestoreVersion && (
          <DisabledWithTooltip isDisabled={!builderPermissions.canEdit} content={builderPermissions.tooltips.edit}>
            <Button
              variant="secondary"
              onClick={onRestoreVersion}
              isAriaDisabled={!builderPermissions.canEdit}
              icon={
                <Icon isInline>
                  <RhUiUndoIcon />
                </Icon>
              }
            >
              Restore version
            </Button>
          </DisabledWithTooltip>
        )}
        <Button variant="primary" onClick={onExitVersionView}>
          Back to editor
        </Button>
        {onToggleVersionHistory && (
          <Button
            variant="plain"
            onClick={onToggleVersionHistory}
            isClicked={versionHistoryOpen}
            aria-pressed={versionHistoryOpen}
            aria-label="Version history"
          >
            <Icon isInline>
              <RhUiClockIcon />
            </Icon>
          </Button>
        )}
      </>
    )
  }

  if (isLiveRunActive && onBackToEditor) {
    return (
      <>
        {hasApprovalPending && onReviewApproval && (
          <Button
            variant="primary"
            isLoading={isApprovalLoading}
            isAriaDisabled={isApprovalPanelOpen}
            onClick={isApprovalPanelOpen ? undefined : onReviewApproval}
          >
            Review approval
          </Button>
        )}
        {isExecutionCancellable(executionStatus) && executionId && projectId && (
          <CancelExecutionButton executionId={executionId} projectId={projectId} />
        )}
        <Button variant="primary" onClick={onBackToEditor}>
          Back to editor
        </Button>
      </>
    )
  }

  return (
    <BuilderEditorToolbar
      isBuiltin={isBuiltin}
      isNew={isNew}
      workflow={workflow}
      isPending={isPending}
      isDirty={isDirty}
      projectId={projectId}
      lastSavedAt={lastSavedAt}
      isKebabOpen={isKebabOpen}
      publishedVersionId={publishedVersionId}
      currentVersionId={currentVersionId}
      workflowName={workflowName}
      workflowDescription={workflowDescription}
      dispatch={dispatch}
      markDirty={markDirty}
      handleToggleHistory={handleToggleHistory}
      handleToggleVersionHistory={handleToggleVersionHistory}
      handleToggleDetails={handleToggleDetails}
      handleSaveWorkflow={handleSaveWorkflow}
      onPublishClick={onPublishClick}
      onUnpublish={onUnpublish}
      onDuplicate={onDuplicate}
      onPendingImport={onPendingImport}
      triggers={triggers}
      isAddNodePanelOpen={isAddNodePanelOpen}
      hasNoWorkflowNodes={hasNoWorkflowNodes}
      builderPermissions={builderPermissions}
      isNodeEditorOpen={isNodeEditorOpen}
    />
  )
}

/**
 * Header props are intentionally flat for this extraction; many fields mirror `BuilderContent` state.
 * Follow-up: consider grouping (e.g. `toolbarHandlers`) or builder-scoped context to trim prop drilling
 * without re-inflating `BuilderContent` cognitive complexity — see PR review discussion.
 */
export type BuilderWorkflowPageHeaderProps = Readonly<{
  workflowName: string
  workflowDescription: string
  isNew: boolean
  workflow: { id: string } | undefined
  isPending: boolean
  isDirty: boolean
  lastSavedAt?: string | null
  isKebabOpen: boolean
  publishedVersionId: string | null
  currentVersionId?: string | null
  isPublishing: boolean
  isCheckingContractChanges?: boolean
  isPublishDisabled?: boolean
  hasContractReviewError?: boolean
  breakingChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  contractChanges?: WorkflowAPI.components['schemas']['TriggerBreakingChanges'][]
  parentWorkflows?: WorkflowAPI.components['schemas']['WorkflowReferenceRead'][]
  onConfirmPublish?: (
    publishName?: string,
    description?: string,
    onSettled?: () => void,
    callOptions?: { confirm?: boolean }
  ) => void
  onCancelBreakingChanges?: () => void
  onReviewOutputContract?: () => void
  isLiveRunActive?: boolean
  executionId?: string | null
  executionStatus?: ExecutionStatus | null
  projectId?: string
  onBackToEditor?: () => void
  hasApprovalPending?: boolean
  isApprovalLoading?: boolean
  isApprovalPanelOpen?: boolean
  onReviewApproval?: () => void
  triggers?: { id: string; name?: string }[]
  isAddNodePanelOpen: boolean
  hasNoWorkflowNodes: boolean
  isBuiltin: boolean
  builderPermissions: BuilderPermissions
  ProjectSelector: ReactNode
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  handleToggleHistory: () => void
  handleToggleVersionHistory: () => void
  handleToggleDetails: () => void
  handleSaveWorkflow: () => Promise<boolean>
  onPublish: (
    publishName?: string,
    description?: string,
    onSettled?: () => void,
    callOptions?: { confirm?: boolean }
  ) => void
  onUnpublish: () => void
  onDuplicate: () => void
  isViewingVersion?: boolean
  versionHistoryOpen?: boolean
  viewedVersionDate?: string | null
  viewedVersionStatus?: string | null
  onExitVersionView?: () => void
  onRestoreVersion?: () => void
  onPendingImport: (data: PendingImportData) => void
  isNodeEditorOpen?: boolean
}>

/**
 * Builder page title row (name, project, details) and primary toolbar actions.
 */
export function BuilderWorkflowPageHeader({
  workflowName,
  workflowDescription,
  isNew,
  workflow,
  isPending,
  isDirty,
  lastSavedAt,
  isKebabOpen,
  publishedVersionId,
  currentVersionId,
  isPublishing,
  isCheckingContractChanges = false,
  isPublishDisabled = false,
  hasContractReviewError = false,
  breakingChanges,
  contractChanges,
  parentWorkflows,
  onConfirmPublish,
  onCancelBreakingChanges,
  onReviewOutputContract,
  isLiveRunActive,
  executionId,
  executionStatus,
  projectId,
  onBackToEditor,
  hasApprovalPending,
  isApprovalLoading,
  isApprovalPanelOpen,
  onReviewApproval,
  triggers,
  isAddNodePanelOpen,
  hasNoWorkflowNodes,
  isBuiltin,
  builderPermissions,
  ProjectSelector,
  dispatch,
  markDirty,
  handleToggleHistory,
  handleToggleVersionHistory,
  handleToggleDetails,
  handleSaveWorkflow,
  onPublish,
  onUnpublish,
  onDuplicate,
  isViewingVersion,
  versionHistoryOpen,
  viewedVersionDate,
  viewedVersionStatus,
  onExitVersionView,
  onRestoreVersion,
  onPendingImport,
  isNodeEditorOpen,
}: BuilderWorkflowPageHeaderProps) {
  const builderDocLink = useDocLink('builder')
  const publishDialog = useDialogState<true>()
  const {
    removedTriggerNodeIds,
    isLoading: triggerDiffLoading,
    isError: triggerDiffError,
  } = useRemovedSubworkflowTriggerIds(workflow?.id, publishDialog.isOpen)

  const toolbar = (
    <BuilderToolbarContent
      isBuiltin={isBuiltin}
      isLiveRunActive={isLiveRunActive}
      executionId={executionId}
      executionStatus={executionStatus}
      projectId={projectId}
      hasApprovalPending={hasApprovalPending}
      isApprovalLoading={isApprovalLoading}
      isApprovalPanelOpen={isApprovalPanelOpen}
      onBackToEditor={onBackToEditor}
      onReviewApproval={onReviewApproval}
      dispatch={dispatch}
      markDirty={markDirty}
      handleToggleHistory={handleToggleHistory}
      handleToggleVersionHistory={handleToggleVersionHistory}
      isNew={isNew}
      workflow={workflow}
      isPending={isPending}
      isDirty={isDirty}
      lastSavedAt={lastSavedAt}
      isKebabOpen={isKebabOpen}
      publishedVersionId={publishedVersionId}
      currentVersionId={currentVersionId}
      handleToggleDetails={handleToggleDetails}
      handleSaveWorkflow={handleSaveWorkflow}
      onPublishClick={() => {
        publishDialog.open(true)
        onReviewOutputContract?.()
      }}
      onUnpublish={onUnpublish}
      onDuplicate={onDuplicate}
      onPendingImport={onPendingImport}
      triggers={triggers}
      isAddNodePanelOpen={isAddNodePanelOpen}
      hasNoWorkflowNodes={hasNoWorkflowNodes}
      workflowName={workflowName}
      workflowDescription={workflowDescription}
      builderPermissions={builderPermissions}
      isViewingVersion={isViewingVersion}
      versionHistoryOpen={versionHistoryOpen}
      onExitVersionView={onExitVersionView}
      onRestoreVersion={onRestoreVersion}
      onToggleVersionHistory={handleToggleVersionHistory}
      isNodeEditorOpen={isNodeEditorOpen}
    />
  )

  const titleSegment = isNew ? 'New Workflow' : workflowName
  const dirtyTitle = isDirty ? `● ${titleSegment}` : titleSegment

  return (
    <>
      <SynPageTitle segments={[dirtyTitle, 'Workflows']} />
      {isViewingVersion ? (
        <SynPageHeader
          title={workflowName}
          docLink={builderDocLink}
          titleProps={{ size: TitleSizes['2xl'] }}
          titleAddons={
            builderVersionViewHasTitleRowExtras(viewedVersionDate, viewedVersionStatus) ? (
              <BuilderVersionViewTitleRowAddons
                viewedVersionDate={viewedVersionDate}
                viewedVersionStatus={viewedVersionStatus}
              />
            ) : undefined
          }
          toolbar={toolbar}
        />
      ) : (
        <SynPageHeader
          title={workflowName}
          docLink={builderDocLink}
          titleSlot={
            <BuilderEditorTitleSlot
              workflowName={workflowName}
              workflowDescription={workflowDescription}
              workflowId={workflow?.id}
              isNew={isNew}
              publishedVersionId={publishedVersionId}
              currentVersionId={currentVersionId}
              isBuiltin={isBuiltin}
              builderPermissions={builderPermissions}
              ProjectSelector={ProjectSelector}
              dispatch={dispatch}
              markDirty={markDirty}
            />
          }
          toolbar={toolbar}
        />
      )}

      <PublishWorkflowDialog
        isOpen={publishDialog.isOpen}
        isPublishing={isPublishing}
        isCheckingContractChanges={isCheckingContractChanges}
        isPublishDisabled={isPublishDisabled}
        hasContractReviewError={hasContractReviewError}
        onRetryContractReview={onReviewOutputContract}
        breakingChanges={breakingChanges}
        contractChanges={contractChanges}
        parentWorkflows={parentWorkflows}
        onClose={publishDialog.close}
        onConfirmContractChanges={(publishName, description, options) =>
          onConfirmPublish?.(publishName, description, publishDialog.close, options)
        }
        onCancelBreakingChanges={onCancelBreakingChanges}
        onPublish={(publishName, description, options) => {
          onPublish(publishName, description, publishDialog.close, { confirm: options?.confirm })
        }}
        workflowId={workflow?.id}
        removedTriggerNodeIds={removedTriggerNodeIds}
        triggerDiffLoading={triggerDiffLoading}
        triggerDiffError={triggerDiffError}
      />
    </>
  )
}
