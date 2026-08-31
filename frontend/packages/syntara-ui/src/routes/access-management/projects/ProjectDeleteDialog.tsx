import { List, ListItem, Stack, StackItem } from '@patternfly/react-core'
import { useId } from 'react'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'

const DESTRUCTIVE_ACK_LABEL = 'I understand this project and the resources listed above will be permanently deleted.'

export type ProjectDeleteDialogProps = Readonly<{
  isOpen: boolean
  projectName: string | undefined
  onClose: () => void
  onConfirm: () => void
  confirmLoading?: boolean
}>

/**
 * Delete confirmation for a project — shared by ProjectsTab, ProjectDetail, and WorkflowDialogs.
 */
export function ProjectDeleteDialog({
  isOpen,
  projectName,
  onClose,
  onConfirm,
  confirmLoading,
}: ProjectDeleteDialogProps) {
  const ackCheckboxId = useId()

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Delete project?"
      confirmLabel="Delete"
      confirmVariant="danger"
      titleIconVariant="warning"
      confirmLoading={confirmLoading}
      destructiveAcknowledgement={{
        checkboxId: ackCheckboxId,
        label: DESTRUCTIVE_ACK_LABEL,
      }}
    >
      <Stack hasGutter>
        <StackItem>
          The project <strong>{projectName}</strong> will be deleted. This cannot be undone.
        </StackItem>
        <StackItem>Resources that will be deleted:</StackItem>
        <StackItem>
          <List>
            <ListItem>Workflows, executions, and approval requests</ListItem>
            <ListItem>Credentials and service accounts</ListItem>
            <ListItem>Uploaded files</ListItem>
            <ListItem>Role assignments, project roles, and policies</ListItem>
            <ListItem>Integration assignments for this project</ListItem>
          </List>
        </StackItem>
      </Stack>
    </SynConfirmationDialog>
  )
}
