import { Content, Stack, StackItem } from '@patternfly/react-core'
import { useId } from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import { useWorkflowUsedBy } from './useWorkflowUsedBy'
import { WorkflowReferencedParentsAlert } from './WorkflowReferencedParentsAlert'

const DELETE_WORKFLOW_ACK_LABEL =
  'I understand this workflow will be deleted, any in-progress runs will stop immediately, and any workflows that use it as a sub-workflow will no longer be able to call it.'

export type WorkflowDeleteDialogProps = Readonly<{
  isOpen: boolean
  workflowName: string
  workflowId?: string
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
  workflowId,
  onClose,
  onConfirm,
  confirmLoading,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
}: WorkflowDeleteDialogProps) {
  const ackCheckboxId = useId()
  const {
    totalCount,
    isError,
    isLoading: isUsedByLoading,
  } = useWorkflowUsedBy(workflowId, {
    enabled: isOpen,
  })
  const referencedTitle = `This workflow is used as a sub-workflow by ${totalCount} published ${totalCount === 1 ? 'workflow' : 'workflows'}`

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Delete workflow?"
      confirmLabel="Delete workflow"
      confirmVariant="danger"
      titleIconVariant="warning"
      confirmLoading={confirmLoading}
      confirmDisabled={isUsedByLoading}
      aria-labelledby={ariaLabelledby}
      aria-describedby={ariaDescribedby}
      destructiveAcknowledgement={{
        checkboxId: ackCheckboxId,
        label: DELETE_WORKFLOW_ACK_LABEL,
      }}
    >
      <Stack hasGutter>
        <StackItem>
          <Content component="p">
            The workflow <strong>{workflowName}</strong> will be deleted and any in-progress runs will stop immediately.
            This action cannot be undone.
          </Content>
        </StackItem>
        {(totalCount > 0 || isError) && (
          <StackItem>
            <WorkflowReferencedParentsAlert
              totalCount={totalCount}
              isError={isError}
              title={referencedTitle}
              consequence="Deleting it means they will no longer be able to call it as a sub-workflow."
            />
          </StackItem>
        )}
      </Stack>
    </SynConfirmationDialog>
  )
}
