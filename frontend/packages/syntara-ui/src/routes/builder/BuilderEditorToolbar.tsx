import { Button, Divider, Dropdown, Icon, MenuToggle, type MenuToggleElement } from '@patternfly/react-core'
import { RhUiEllipsisVerticalFillIcon, RhUiAddSquareIcon } from '@patternfly/react-icons'
import { useCallback, type Dispatch, type Ref } from 'react'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { useWorkflowStore } from '../../stores/useWorkflowStore'

import type { BuilderAction } from './builderReducer'
import { KebabMenuViewsGroup, KebabMenuActionsGroup } from './kebabMenuItems'
import { PublishWorkflowButton } from './PublishWorkflowButton'
import { RunWorkflowSection } from './RunWorkflowSection'
import { SaveWorkflowButton } from './SaveWorkflowButton'
import type { BuilderPermissions } from './useBuilderPermissions'
import { useWorkflowImportExport, type PendingImportData } from './useWorkflowImportExport'

type WorkflowKebabToggleProps = Readonly<{
  toggleRef: Ref<MenuToggleElement>
  isKebabOpen: boolean
  dispatch: Dispatch<BuilderAction>
}>

function WorkflowKebabToggle({ toggleRef, isKebabOpen, dispatch }: WorkflowKebabToggleProps) {
  return (
    <MenuToggle
      ref={toggleRef}
      variant="plain"
      onClick={() => dispatch({ type: 'SET_KEBAB_OPEN', payload: !isKebabOpen })}
      isExpanded={isKebabOpen}
      aria-label="Workflow actions"
    >
      <RhUiEllipsisVerticalFillIcon />
    </MenuToggle>
  )
}

type WorkflowKebabMenuProps = Readonly<{
  isBuiltin: boolean
  isNew: boolean
  workflow: { id: string } | undefined
  isKebabOpen: boolean
  publishedVersionId: string | null
  dispatch: Dispatch<BuilderAction>
  handleToggleHistory: () => void
  handleToggleVersionHistory: () => void
  handleToggleDetails: () => void
  onUnpublish: () => void
  builderPermissions: BuilderPermissions
  importFileRef: React.RefObject<HTMLInputElement | null>
  handleImportFile: (event: React.ChangeEvent<HTMLInputElement>) => void
  handleExport: () => void
  handleVerify: (onValid?: () => void) => void
  handleDuplicate: () => void
}>

function WorkflowKebabMenu({
  isBuiltin,
  isNew,
  workflow,
  isKebabOpen,
  publishedVersionId,
  dispatch,
  handleToggleHistory,
  handleToggleVersionHistory,
  handleToggleDetails,
  onUnpublish,
  builderPermissions,
  importFileRef,
  handleImportFile,
  handleExport,
  handleVerify,
  handleDuplicate,
}: WorkflowKebabMenuProps) {
  const renderKebabMenuToggle = useCallback(
    (toggleRef: Ref<MenuToggleElement>) => (
      <WorkflowKebabToggle toggleRef={toggleRef} isKebabOpen={isKebabOpen} dispatch={dispatch} />
    ),
    [dispatch, isKebabOpen]
  )
  const showExistingWorkflowItems = !isNew && !!workflow?.id
  const closeKebab = () => dispatch({ type: 'SET_KEBAB_OPEN', payload: false })

  return (
    <>
      <Dropdown
        isOpen={isKebabOpen}
        onOpenChange={(isOpen) => dispatch({ type: 'SET_KEBAB_OPEN', payload: isOpen })}
        popperProps={{ position: 'right' }}
        toggle={renderKebabMenuToggle}
      >
        <KebabMenuViewsGroup
          showExistingWorkflowItems={showExistingWorkflowItems}
          handleToggleHistory={handleToggleHistory}
          handleToggleVersionHistory={handleToggleVersionHistory}
          handleToggleDetails={handleToggleDetails}
          closeKebab={closeKebab}
        />
        {!isBuiltin && <Divider />}
        {!isBuiltin && (
          <KebabMenuActionsGroup
            showExistingWorkflowItems={showExistingWorkflowItems}
            publishedVersionId={publishedVersionId}
            canEdit={builderPermissions.canEdit}
            canCreate={builderPermissions.canCreate}
            canDelete={builderPermissions.canDelete}
            tooltips={builderPermissions.tooltips}
            handleVerify={handleVerify}
            handleDuplicate={handleDuplicate}
            handleExport={handleExport}
            importFileRef={importFileRef}
            onUnpublish={onUnpublish}
            dispatch={dispatch}
            closeKebab={closeKebab}
          />
        )}
      </Dropdown>
      <input ref={importFileRef} type="file" accept=".json" onChange={handleImportFile} style={{ display: 'none' }} />
    </>
  )
}

type BuilderEditorToolbarProps = Readonly<{
  isBuiltin: boolean
  isNew: boolean
  workflow: { id: string } | undefined
  isPending: boolean
  isDirty: boolean
  lastSavedAt?: string | null
  isKebabOpen: boolean
  publishedVersionId: string | null
  currentVersionId?: string | null
  isAddNodePanelOpen: boolean
  hasNoWorkflowNodes: boolean
  workflowName: string
  workflowDescription: string
  dispatch: Dispatch<BuilderAction>
  markDirty: () => void
  handleToggleHistory: () => void
  handleToggleVersionHistory: () => void
  handleToggleDetails: () => void
  handleSaveWorkflow: () => Promise<boolean>
  onPublishClick: () => void
  onUnpublish: () => void
  onDuplicate: () => void
  onPendingImport: (data: PendingImportData) => void
  triggers?: { id: string; name?: string }[]
  builderPermissions: BuilderPermissions
  isNodeEditorOpen?: boolean
}>

export function BuilderEditorToolbar({
  isBuiltin,
  isNew,
  workflow,
  isPending,
  isDirty,
  lastSavedAt,
  isKebabOpen,
  publishedVersionId,
  currentVersionId,
  isAddNodePanelOpen,
  hasNoWorkflowNodes,
  workflowName,
  workflowDescription,
  dispatch,
  markDirty,
  handleToggleHistory,
  handleToggleVersionHistory,
  handleToggleDetails,
  handleSaveWorkflow,
  onPublishClick,
  onUnpublish,
  onDuplicate,
  onPendingImport,
  triggers,
  builderPermissions,
  isNodeEditorOpen,
}: BuilderEditorToolbarProps) {
  const { importFileRef, handleImportFile, handleExport, handleVerify, isVerifying, validationErrorCount } =
    useWorkflowImportExport({
      dispatch,
      markDirty,
      isNew,
      workflowName,
      workflowDescription,
      onPendingImport,
    })

  const hasNoSteps = useWorkflowStore((s) => (s.currentWorkflow?.workflow?.activities?.length ?? 0) === 0)
  const hasNoChanges = publishedVersionId != null && publishedVersionId === currentVersionId && !isDirty

  const showAddStep = !hasNoWorkflowNodes
  const showWorkflowActions = !isNew && !!workflow?.id

  if (!builderPermissions.canEdit && hasNoWorkflowNodes && isNew) {
    return null
  }

  if (isBuiltin) {
    return (
      <WorkflowKebabMenu
        isBuiltin={isBuiltin}
        isNew={isNew}
        workflow={workflow}
        isKebabOpen={isKebabOpen}
        publishedVersionId={publishedVersionId}
        dispatch={dispatch}
        handleToggleHistory={handleToggleHistory}
        handleToggleVersionHistory={handleToggleVersionHistory}
        handleToggleDetails={handleToggleDetails}
        onUnpublish={onUnpublish}
        builderPermissions={builderPermissions}
        importFileRef={importFileRef}
        handleImportFile={handleImportFile}
        handleExport={handleExport}
        handleVerify={handleVerify}
        handleDuplicate={onDuplicate}
      />
    )
  }

  return (
    <>
      {showAddStep && (
        <DisabledWithTooltip isDisabled={!builderPermissions.canEdit} content={builderPermissions.tooltips.edit}>
          <Button
            variant="plain"
            isClicked={isAddNodePanelOpen}
            aria-pressed={isAddNodePanelOpen}
            isAriaDisabled={!builderPermissions.canEdit}
            onClick={
              builderPermissions.canEdit
                ? () => {
                    dispatch({
                      type: 'OPEN_ADD_NODE_PANEL',
                      payload: { sourceNodeId: null, replacementNodeId: null },
                    })
                  }
                : undefined
            }
            icon={
              <Icon isInline>
                <RhUiAddSquareIcon />
              </Icon>
            }
            iconPosition="start"
          >
            Add step
          </Button>
        </DisabledWithTooltip>
      )}

      {showAddStep && <Divider orientation={{ default: 'vertical' }} />}
      <RunWorkflowSection
        triggers={triggers}
        isSaved={!!workflow?.id}
        validationErrorCount={validationErrorCount}
        dispatch={dispatch}
        builderPermissions={builderPermissions}
        isNodeEditorOpen={isNodeEditorOpen}
      />

      <Divider orientation={{ default: 'vertical' }} />

      <SaveWorkflowButton
        isPending={isPending}
        isDirty={isDirty}
        isNew={isNew}
        lastSavedAt={lastSavedAt}
        onSave={handleSaveWorkflow}
        canEdit={builderPermissions.canEdit}
        editTooltip={builderPermissions.tooltips.save}
        isNodeEditorOpen={isNodeEditorOpen}
      />

      {showWorkflowActions && (
        <>
          <Divider orientation={{ default: 'vertical' }} />
          <PublishWorkflowButton
            canEdit={builderPermissions.canEdit}
            hasNoSteps={hasNoSteps}
            hasNoChanges={hasNoChanges}
            validationErrorCount={validationErrorCount}
            isVerifying={isVerifying}
            editTooltip={builderPermissions.tooltips.publish}
            handleVerify={handleVerify}
            onPublishClick={onPublishClick}
            isNodeEditorOpen={isNodeEditorOpen}
          />
        </>
      )}

      {isVerifying && (
        <>
          <Divider orientation={{ default: 'vertical' }} />
          <Button variant="plain" isLoading isAriaDisabled>
            Verifying...
          </Button>
        </>
      )}

      <Divider orientation={{ default: 'vertical' }} />
      <WorkflowKebabMenu
        isBuiltin={isBuiltin}
        isNew={isNew}
        workflow={workflow}
        isKebabOpen={isKebabOpen}
        publishedVersionId={publishedVersionId}
        dispatch={dispatch}
        handleToggleHistory={handleToggleHistory}
        handleToggleVersionHistory={handleToggleVersionHistory}
        handleToggleDetails={handleToggleDetails}
        onUnpublish={onUnpublish}
        builderPermissions={builderPermissions}
        importFileRef={importFileRef}
        handleImportFile={handleImportFile}
        handleExport={handleExport}
        handleVerify={handleVerify}
        handleDuplicate={onDuplicate}
      />
    </>
  )
}
