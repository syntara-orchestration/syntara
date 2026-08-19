import { Button, Flex, FlexItem, Icon, TextInput, TitleSizes, Tooltip } from '@patternfly/react-core'
import { RhUiClockIcon, RhUiUndoIcon } from '@patternfly/react-icons'
import type { ExecutionStatus } from '@syntara/contracts'
import { type Dispatch, type ReactNode } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { NxPageHeader } from '../../components/layout/NxPageHeader'
import { NxPageTitle } from '../../components/NxPageTitle'
import { WorkflowPublishStatusBadge } from '../../components/WorkflowPublishStatusBadge'
import { useDialogState } from '../../hooks/useDialogState'
import { useDocLink } from '../../utils/docs/useDocLink'
import { CancelExecutionButton } from '../executions/CancelExecutionButton'
import { isExecutionCancellable } from '../executions/executionCancellable'

import { BuilderEditorToolbar } from './BuilderEditorToolbar'
import type { BuilderAction } from './builderReducer'
import { BuilderVersionViewTitleRowAddons } from './BuilderWorkflowPageHeaderParts'
import { builderVersionViewHasTitleRowExtras } from './builderWorkflowPageHeaderTitle'
import { EditWorkflowDetailsPopover } from './EditWorkflowDetailsPopover'
import { PublishWorkflowDialog } from './PublishWorkflowDialog'
import type { BuilderPermissions } from './useBuilderPermissions'
import type { PendingImportData } from './useWorkflowImportExport'

type BuilderToolbarContentProps = Readonly<{
  isLiveRunActive?: boolean
  executionId?: string | null
  executionStatus?: ExecutionStatus | null
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
    const isCancellable = isExecutionCancellable(executionStatus)
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
        {isCancellable && executionId && <CancelExecutionButton executionId={executionId} />}
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
      onPendingImport={onPendingImport}
      triggers={triggers}
      isAddNodePanelOpen={isAddNodePanelOpen}
      hasNoWorkflowNodes={hasNoWorkflowNodes}
      builderPermissions={builderPermissions}
      isNodeEditorOpen={isNodeEditorOpen}
    />
  )
}

function BuilderEditorTitleSlot({
  workflowName,
  workflowDescription,
  isNew,
  publishedVersionId,
  currentVersionId,
  isBuiltin,
  builderPermissions,
  ProjectSelector,
  dispatch,
  markDirty,
}: Readonly<{
  workflowName: string
  workflowDescription: string
  isNew: boolean
  publishedVersionId: string | null
  currentVersionId?: string | null
  isBuiltin: boolean
  builderPermissions: BuilderPermissions
  ProjectSelector: ReactNode
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
}>) {
  return (
    <Flex
      gap={{ default: 'gapMd' }}
      alignItems={{ default: 'alignItemsCenter' }}
      flexWrap={{ default: 'nowrap' }}
      style={{ height: '100%' }}
    >
      <FlexItem style={{ flexShrink: 1, minWidth: 0 }}>
        <Tooltip
          content={builderPermissions.tooltips.edit}
          trigger={builderPermissions.canEdit ? 'manual' : 'mouseenter focus'}
        >
          <TextInput
            id="workflow-name-input"
            type="text"
            aria-label="Workflow name"
            value={workflowName}
            isDisabled={!builderPermissions.canEdit}
            onChange={(_event, value) => {
              dispatch({ type: 'SET_WORKFLOW_NAME', payload: value })
              markDirty()
            }}
            placeholder="Workflow name"
          />
        </Tooltip>
      </FlexItem>
      {builderPermissions.canEdit && (
        <FlexItem style={{ flexShrink: 0 }}>
          <EditWorkflowDetailsPopover
            name={workflowName}
            description={workflowDescription}
            onApply={(name, description) => {
              const nameChanged = name !== workflowName
              const descriptionChanged = description !== workflowDescription
              if (nameChanged) dispatch({ type: 'SET_WORKFLOW_NAME', payload: name })
              if (descriptionChanged) dispatch({ type: 'SET_WORKFLOW_DESCRIPTION', payload: description })
              if (nameChanged || descriptionChanged) markDirty()
            }}
          />
        </FlexItem>
      )}
      {!isNew && (
        <FlexItem style={{ flexShrink: 0 }}>
          <WorkflowPublishStatusBadge publishedVersionId={publishedVersionId} currentVersionId={currentVersionId} />
        </FlexItem>
      )}
      {(builderPermissions.canEdit || isBuiltin) && <FlexItem style={{ flexShrink: 0 }}>{ProjectSelector}</FlexItem>}
    </Flex>
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
  isLiveRunActive?: boolean
  executionId?: string | null
  executionStatus?: ExecutionStatus | null
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
  onPublish: (publishName?: string, description?: string, onSettled?: () => void) => void
  onUnpublish: () => void
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
  isLiveRunActive,
  executionId,
  executionStatus,
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

  const toolbar = (
    <BuilderToolbarContent
      isBuiltin={isBuiltin}
      isLiveRunActive={isLiveRunActive}
      executionId={executionId}
      executionStatus={executionStatus}
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
      onPublishClick={() => publishDialog.open(true)}
      onUnpublish={onUnpublish}
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
      <NxPageTitle segments={[dirtyTitle, 'Workflows']} />
      {isViewingVersion ? (
        <NxPageHeader
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
        <NxPageHeader
          title={workflowName}
          docLink={builderDocLink}
          titleSlot={
            <BuilderEditorTitleSlot
              workflowName={workflowName}
              workflowDescription={workflowDescription}
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
        onClose={publishDialog.close}
        onPublish={(publishName, description) => {
          onPublish(publishName, description, publishDialog.close)
        }}
      />
    </>
  )
}
