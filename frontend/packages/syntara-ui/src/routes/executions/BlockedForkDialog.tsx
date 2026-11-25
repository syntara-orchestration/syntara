import { Content } from '@patternfly/react-core'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import type { BlockedFork } from './forkStepTypes'

type BlockedForkDialogProps = {
  /** The pending fork, or null when no prompt is needed. */
  blockedFork: BlockedFork | null
  onConfirm: () => void
  onCancel: () => void
  /** The fork is being created. */
  isLoading?: boolean
}

/** Asks whether to fork a run as a new workflow without the step types the user may not write. */
export function BlockedForkDialog({
  blockedFork,
  onConfirm,
  onCancel,
  isLoading = false,
}: Readonly<BlockedForkDialogProps>) {
  return (
    <SynConfirmationDialog
      isOpen={Boolean(blockedFork)}
      onClose={onCancel}
      onConfirm={onConfirm}
      title="Some steps can't be forked"
      titleIconVariant="warning"
      confirmLabel="Fork without those steps"
      cancelLabel="Cancel"
      confirmLoading={isLoading}
    >
      <Content component="p">
        You don&apos;t have permission to write these step types: {blockedFork?.labels.join(', ')}. Fork the run without
        those steps?
      </Content>
      <Content component="p">
        Connections to those steps will be removed. Review and reconnect the affected steps after forking.
      </Content>
      {blockedFork?.losesAllTriggers && (
        <Content component="p">
          No trigger will be copied. Add a permitted trigger before running this workflow.
        </Content>
      )}
    </SynConfirmationDialog>
  )
}
