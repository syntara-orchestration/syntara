import { Content } from '@patternfly/react-core'

import { SynConfirmationDialog } from '../../../components/dialogs/SynConfirmationDialog'
import type { BlockedRunCopy } from '../hooks/useExecutionCopyToEditor'

type BlockedRunCopyDialogProps = {
  /** The pending copy, or null when no prompt is needed. */
  blockedRunCopy: BlockedRunCopy | null
  onConfirm: () => void
  onCancel: () => void
}

/** Asks whether to copy a run to the editor without the step types the user may not write. */
export function BlockedRunCopyDialog({ blockedRunCopy, onConfirm, onCancel }: Readonly<BlockedRunCopyDialogProps>) {
  return (
    <SynConfirmationDialog
      isOpen={blockedRunCopy !== null}
      onClose={onCancel}
      onConfirm={onConfirm}
      title="Some steps can't be copied"
      titleIconVariant="warning"
      confirmLabel="Copy without those steps"
      cancelLabel="Cancel"
    >
      <Content component="p">
        You don&apos;t have permission to write these step types: {blockedRunCopy?.labels.join(', ')}. Copy the run
        without those steps?
      </Content>
      <Content component="p">
        Connections to those steps will be removed. Review and reconnect the affected steps after copying.
      </Content>
      {blockedRunCopy?.losesAllTriggers && (
        <Content component="p">
          No trigger will be copied. Add a permitted trigger before running this workflow.
        </Content>
      )}
    </SynConfirmationDialog>
  )
}
