import { Alert, AlertActionLink, Content, FlexItem } from '@patternfly/react-core'
import type { ReactNode } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { EditVersionDialog } from '../EditVersionDialog'
import type { VersionSidePanelState } from '../hooks/useBuilderVersionPanel'
import { PublishWorkflowDialog } from '../PublishWorkflowDialog'
import { SaveBeforeViewDialog } from '../SaveBeforeViewDialog'
import { VersionHistoryPanel } from '../VersionHistoryPanel'

import styles from './VersionHistorySidePanel.module.css'

type RestorePermissionDialog = VersionSidePanelState['restoreDialog']

function restorePermissionMessage(restoreDialog: RestorePermissionDialog): ReactNode {
  if (restoreDialog.permissionCheckError) {
    return (
      <Alert
        variant="danger"
        isInline
        title="Unable to check step-type permissions."
        actionLinks={
          <AlertActionLink onClick={restoreDialog.onRetryPermissionCheck}>Retry permission check</AlertActionLink>
        }
      >
        Restore is disabled until permissions can be checked.
      </Alert>
    )
  }
  if (restoreDialog.blockedStepTypes.length > 0) {
    return (
      <Alert variant="warning" isInline title="The selected version contains blocked step types.">
        Blocked step types: {restoreDialog.blockedStepTypes.join(', ')}.
      </Alert>
    )
  }
  if (restoreDialog.permissionCheckLoading) {
    return <Alert variant="info" isInline title="Checking step-type permissions." />
  }
  return (
    <Content component="p">
      This will replace your current editor state with the selected version. Any unsaved changes will be lost.
    </Content>
  )
}

type VersionHistorySidePanelProps = Readonly<{
  sidePanel: VersionSidePanelState
  isStepEditorOpen: boolean
  editPermission?: { canEdit: boolean; tooltip: string; canCreate: boolean; createTooltip: string }
  projectId?: string
}>

export function VersionHistorySidePanel({
  sidePanel,
  isStepEditorOpen,
  editPermission,
  projectId,
}: VersionHistorySidePanelProps) {
  return (
    <>
      {!isStepEditorOpen && sidePanel.show && (
        <FlexItem className={styles.sidePanelItem}>
          <VersionHistoryPanel
            versions={sidePanel.filteredVersions}
            selectedVersion={sidePanel.selectedVersion}
            onClose={sidePanel.onClose}
            onSelectVersion={sidePanel.onSelectVersion}
            onRestoreVersion={sidePanel.onRestoreVersion}
            onExportVersion={sidePanel.onExportVersion}
            onOpenInNewWindow={sidePanel.onOpenInNewWindow}
            onPublishVersion={sidePanel.onPublishVersion}
            onViewRunHistory={sidePanel.onViewRunHistory}
            executedVersionNumbers={sidePanel.executedVersionNumbers}
            onEditVersion={sidePanel.onEditVersion}
            onDuplicateVersion={sidePanel.onDuplicateVersion}
            statusFilter={sidePanel.statusFilter}
            onStatusFilterChange={sidePanel.onStatusFilterChange}
            canEdit={editPermission?.canEdit}
            editTooltip={editPermission?.tooltip}
            canCreate={editPermission?.canCreate}
            createTooltip={editPermission?.createTooltip}
            projectId={projectId}
            publishedVersionName={sidePanel.publishedVersionName}
            paginationFooterProps={sidePanel.paginationFooterProps}
          />
        </FlexItem>
      )}

      <PublishWorkflowDialog
        isOpen={sidePanel.publishDialog.isOpen}
        isPublishing={false}
        onClose={sidePanel.publishDialog.onClose}
        onPublish={sidePanel.publishDialog.onPublish}
        canPublish={sidePanel.publishDialog.canPublish}
        editTooltip={sidePanel.publishDialog.editTooltip}
        permissionCheckError={sidePanel.publishDialog.permissionCheckError}
        permissionCheckLoading={sidePanel.publishDialog.permissionCheckLoading}
        blockedStepTypes={sidePanel.publishDialog.blockedStepTypes}
        onRetryPermissionCheck={sidePanel.publishDialog.onRetryPermissionCheck}
      />

      <SaveBeforeViewDialog
        isOpen={sidePanel.saveBeforeViewDialog.isOpen}
        onSave={sidePanel.saveBeforeViewDialog.onSave}
        onViewWithoutSaving={sidePanel.saveBeforeViewDialog.onViewWithoutSaving}
        onCancel={sidePanel.saveBeforeViewDialog.onCancel}
      />

      <EditVersionDialog
        isOpen={sidePanel.editDialog.isOpen}
        isSaving={sidePanel.editDialog.isSaving}
        onClose={sidePanel.editDialog.onClose}
        onSave={sidePanel.editDialog.onSave}
        initialName={sidePanel.editDialog.initialName}
        initialDescription={sidePanel.editDialog.initialDescription}
        canEdit={sidePanel.editDialog.canEdit}
        editTooltip={sidePanel.editDialog.editTooltip}
        permissionCheckError={sidePanel.editDialog.permissionCheckError}
        onRetryPermissionCheck={sidePanel.editDialog.onRetryPermissionCheck}
      />

      {sidePanel.restoreDialog.onConfirm && (
        <SynConfirmationDialog
          isOpen={sidePanel.restoreDialog.isOpen}
          onClose={sidePanel.restoreDialog.onClose}
          onConfirm={sidePanel.restoreDialog.onConfirm}
          title={sidePanel.restoreDialog.title}
          confirmLabel="Restore version"
          titleIconVariant="warning"
          confirmLoading={sidePanel.restoreDialog.isLoading}
          confirmDisabled={!sidePanel.restoreDialog.canConfirm}
        >
          {restorePermissionMessage(sidePanel.restoreDialog)}
        </SynConfirmationDialog>
      )}
    </>
  )
}
