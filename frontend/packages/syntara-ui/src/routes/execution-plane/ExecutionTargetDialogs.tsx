import { Content, ContentVariants } from '@patternfly/react-core'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import type { useExecutionTargetActions } from './useExecutionTargetActions'

type ExecutionTargetDialogsProps = Readonly<{
  deleteDialog: ReturnType<typeof useExecutionTargetActions>['deleteDialog']
  onDelete: () => void
}>

export function ExecutionTargetDialogs({ deleteDialog, onDelete }: ExecutionTargetDialogsProps) {
  return (
    <SynConfirmationDialog
      isOpen={deleteDialog.isOpen}
      onClose={deleteDialog.close}
      onConfirm={onDelete}
      title="Delete execution target?"
      confirmLabel="Delete"
      confirmVariant="danger"
      titleIconVariant="warning"
      destructiveAcknowledgement={{
        checkboxId: 'delete-execution-target-ack',
        label: 'I understand this execution target will be permanently deleted.',
      }}
    >
      <Content component={ContentVariants.p}>
        The execution target <strong>{deleteDialog.item?.name}</strong> will be deleted. This cannot be undone.
      </Content>
    </SynConfirmationDialog>
  )
}
