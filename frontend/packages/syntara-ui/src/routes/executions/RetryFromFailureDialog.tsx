import { Alert, Content, ContentVariants, Spinner } from '@patternfly/react-core'

import { SynConfirmationDialog } from '../../components/dialogs/SynConfirmationDialog'

import { canConfirmRetryFromFailure, describeRetryScope, type RetryFromFailurePreview } from './retryFromFailure'

type RetryFromFailureDialogProps = Readonly<{
  isOpen: boolean
  onClose: () => void
  onConfirm: () => void
  confirmLoading?: boolean
  preview: RetryFromFailurePreview | undefined
  isPreviewLoading: boolean
  isPreviewError: boolean
}>

/**
 * Confirmation for retrying a failed execution from its failure points.
 *
 * Deliberately does not itemize skipped versus re-run steps: the preview
 * endpoint reports per-point counts and a deduplicated total, and no
 * node-by-node breakdown, so anything more detailed here would be invented.
 */
export function RetryFromFailureDialog({
  isOpen,
  onClose,
  onConfirm,
  confirmLoading,
  preview,
  isPreviewLoading,
  isPreviewError,
}: RetryFromFailureDialogProps) {
  const isConfirmDisabled = !canConfirmRetryFromFailure(preview, isPreviewLoading, isPreviewError)
  const rejectionReason = preview && !preview.eligible ? preview.reason : null

  let bodyContent: React.ReactNode

  if (isPreviewLoading) {
    bodyContent = (
      <Content component={ContentVariants.p}>
        <Spinner size="md" aria-label="Checking retry options" /> Checking what can be retried…
      </Content>
    )
  } else if (isPreviewError) {
    bodyContent = (
      <Alert
        isInline
        variant="danger"
        title="Could not check retry options"
        data-testid="retry-preview-error"
      >
        The retry preview could not be loaded. Close this dialog and try again.
      </Alert>
    )
  } else if (rejectionReason) {
    bodyContent = (
      <Alert isInline variant="warning" title="This run cannot be retried from failure" data-testid="retry-rejected">
        {rejectionReason}
      </Alert>
    )
  } else {
    bodyContent = (
      <Content component={ContentVariants.p} data-testid="retry-preview-summary">
        {describeRetryScope(preview)}
      </Content>
    )
  }

  return (
    <SynConfirmationDialog
      isOpen={isOpen}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Retry from failure?"
      confirmLabel="Retry from failure"
      confirmLoading={Boolean(confirmLoading)}
      confirmDisabled={isConfirmDisabled}
      variant="medium"
    >
      {bodyContent}
    </SynConfirmationDialog>
  )
}