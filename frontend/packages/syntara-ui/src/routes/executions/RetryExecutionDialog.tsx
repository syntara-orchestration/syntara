import { Content, ContentVariants, Spinner } from '@patternfly/react-core'
import type React from 'react'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

type RetryExecutionDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  confirmLoading?: boolean
  isCurrentVersion: boolean
  isVersionLoading?: boolean
  versionLabel?: string
}>

export function RetryExecutionDialog({
  isOpen,
  onClose,
  onConfirm,
  confirmLoading,
  isCurrentVersion,
  isVersionLoading,
  versionLabel,
}: RetryExecutionDialogProps) {
  const showOlderVersionCopy = !isVersionLoading && !isCurrentVersion

  let bodyContent: React.ReactNode
  if (isVersionLoading) {
    bodyContent = (
      <Content component={ContentVariants.p}>
        <Spinner size="md" aria-label="Checking version" /> Checking workflow version…
      </Content>
    )
  } else if (showOlderVersionCopy) {
    bodyContent = (
      <Content component={ContentVariants.p}>
        This run used an older version of the workflow ({versionLabel}). Retrying will re-execute that same version, not
        the latest one.
      </Content>
    )
  } else {
    bodyContent = (
      <Content component={ContentVariants.p}>
        You are about to retry this workflow run. The workflow will re-execute and you can track its progress in the run
        details.
      </Content>
    )
  }

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Retry run?"
      confirmLabel={showOlderVersionCopy ? 'Retry original version' : 'Retry run'}
      confirmLoading={confirmLoading}
    >
      {bodyContent}
    </SynConfirmationDialog>
  )
}
