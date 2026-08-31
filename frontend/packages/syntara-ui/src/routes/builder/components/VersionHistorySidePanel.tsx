import { Content, FlexItem } from '@patternfly/react-core'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import { EditVersionDialog } from '../EditVersionDialog'
import type { VersionSidePanelState } from '../hooks/useBuilderVersionPanel'
import { PublishWorkflowDialog } from '../PublishWorkflowDialog'
import { SaveBeforeViewDialog } from '../SaveBeforeViewDialog'
import { VersionHistoryPanel } from '../VersionHistoryPanel'

import styles from './VersionHistorySidePanel.module.css'

type VersionHistorySidePanelProps = Readonly<{
  sidePanel: VersionSidePanelState
  isNodeEditorOpen: boolean
  editPermission?: { canEdit: boolean; tooltip: string }
}>

export function VersionHistorySidePanel({ sidePanel, isNodeEditorOpen, editPermission }: VersionHistorySidePanelProps) {
  return (
    <>
      {!isNodeEditorOpen && sidePanel.show && (
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
      />

      {sidePanel.restoreDialog.onConfirm && (
        <SynConfirmationDialog
          isOpen={sidePanel.restoreDialog.isOpen}
          onClose={sidePanel.restoreDialog.onClose}
          onConfirm={sidePanel.restoreDialog.onConfirm}
          title={sidePanel.restoreDialog.title}
          confirmLabel="Restore"
          titleIconVariant="warning"
          confirmLoading={sidePanel.restoreDialog.isLoading}
        >
          <Content component="p">
            This will replace your current editor state with the selected version. Any unsaved changes will be lost.
          </Content>
        </SynConfirmationDialog>
      )}
    </>
  )
}
