import { Button } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'
import { useDialogState } from '../../hooks/useDialogState'
import { detachPromise } from '../../utils/detachPromise'

import { useRetryFromFailure } from './hooks/useRetryFromFailure'
import { useRetryFromFailurePreview } from './hooks/useRetryFromFailurePreview'
import { RetryFromFailureDialog } from './RetryFromFailureDialog'

type RetryFromFailureButtonProps = Readonly<{
  executionId: string
  projectId: string
}>

const retryTooltip = permissionTooltip('retry this execution from failure', 'execution:run')

/**
 * "Retry from failure" action for a failed execution.
 *
 * Opens a dialog that previews the retry before the operator commits, then
 * navigates to the resulting execution. Rendered only for executions the
 * backend accepts a retry-from-failure for; see `isRetryFromFailureEligible`.
 */
export function RetryFromFailureButton({ executionId, projectId }: Readonly<RetryFromFailureButtonProps>) {
  const dialog = useDialogState<void>()
  const navigate = useNavigate()
  // Bumped per open so a reopened dialog refetches the preview rather than
  // showing the previous verdict.
  const [previewNonce, setPreviewNonce] = useState(0)

  /* v8 ignore start -- v8 emits phantom branches from the compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', { resourceProject: projectId })
  const permissionDenied = !isChecking && !canRun
  const isDisabled = !canRun || isChecking
  /* v8 ignore stop */

  const { preview, isLoading, isError } = useRetryFromFailurePreview({
    executionId,
    enabled: dialog.isOpen,
  })

  const retry = useRetryFromFailure({
    executionId,
    onSuccess: (newExecutionId) => {
      dialog.close()
      detachPromise(navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newExecutionId) }))
    },
  })

  function handleOpen() {
    setPreviewNonce((nonce) => nonce + 1)
    dialog.open(undefined)
  }

  return (
    <>
      <DisabledWithTooltip isDisabled={permissionDenied} content={retryTooltip}>
        <Button
          variant="secondary"
          onClick={isDisabled ? undefined : handleOpen}
          isAriaDisabled={isDisabled}
          data-testid="retry-from-failure-button"
        >
          Retry from failure
        </Button>
      </DisabledWithTooltip>
      {/* `key` forces a fresh preview fetch each time the dialog reopens. */}
      <RetryFromFailureDialog
        key={previewNonce}
        isOpen={dialog.isOpen}
        onClose={dialog.close}
        onConfirm={retry.handleRetry}
        confirmLoading={retry.isPending}
        preview={preview}
        isPreviewLoading={isLoading}
        isPreviewError={isError}
      />
    </>
  )
}
