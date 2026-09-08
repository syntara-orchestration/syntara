import { Content } from '@patternfly/react-core'
import { useId } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

const DELETE_WORKFLOW_ACK_LABEL =
  'I understand this workflow will be deleted and any in-progress runs will stop immediately.'

export type WorkflowDeleteDialogProps = Readonly<{
  isOpen: boolean
  workflowName: string
  onClose: () => void
  onConfirm: () => void
  confirmLoading?: boolean
  'aria-labelledby'?: string
  'aria-describedby'?: string
}>

/**
 * Delete confirmation for a workflow — shared by the workflows list and the builder.
 */
export function WorkflowDeleteDialog({
  isOpen,
  workflowName,
  onClose,
  onConfirm,
  confirmLoading,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
}: WorkflowDeleteDialogProps) {
  const ackCheckboxId = useId()

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Delete workflow?"
      confirmLabel="Delete"
      confirmVariant="danger"
      titleIconVariant="warning"
      confirmLoading={confirmLoading}
      aria-labelledby={ariaLabelledby}
      aria-describedby={ariaDescribedby}
      destructiveAcknowledgement={{
        checkboxId: ackCheckboxId,
        label: DELETE_WORKFLOW_ACK_LABEL,
      }}
    >
      <Content component="p">
        The workflow <strong>{workflowName}</strong> will be deleted and any in-progress runs will stop immediately.
        This action cannot be undone.
      </Content>
    </SynConfirmationDialog>
  )
}
