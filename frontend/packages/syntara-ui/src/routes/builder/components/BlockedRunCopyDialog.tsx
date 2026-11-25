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
    </SynConfirmationDialog>
  )
}
