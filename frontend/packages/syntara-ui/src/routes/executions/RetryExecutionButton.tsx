import { Button } from '@patternfly/react-core'
import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'
import { useDialogState } from '../../hooks/useDialogState'
import { detachPromise } from '../../utils/detachPromise'

import { useIsCurrentVersion } from './hooks/useIsCurrentVersion'
import { RetryExecutionDialog } from './RetryExecutionDialog'
import { useRetryExecution } from './useRetryExecution'

type RetryExecutionButtonProps = Readonly<{
  executionId: string
  workflowId: string
  workflowVersionId: string
  projectId: string
}>

const retryTooltip = permissionTooltip('retry this execution', 'execution:run')

export function RetryExecutionButton({
  executionId,
  workflowId,
  workflowVersionId,
  projectId,
}: RetryExecutionButtonProps) {
  const retryDialog = useDialogState<void>()
  const navigate = useNavigate()

  /* v8 ignore start -- v8 emits phantom branches from compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', { resourceProject: projectId })
  const permissionDenied = !isChecking && !canRun
  const isDisabled = !canRun || isChecking

  const {
    isCurrentVersion,
    versionLabel,
    isLoading: isVersionLoading,
  } = useIsCurrentVersion(workflowId, workflowVersionId, retryDialog.isOpen)

  const retry = useRetryExecution(executionId, (newExecutionId) => {
    retryDialog.close()
    detachPromise(navigate({ to: AppRoute.Executions.Execution.replace(':executionId', newExecutionId) }))
  })
  /* v8 ignore stop */

  return (
    <>
      <DisabledWithTooltip isDisabled={permissionDenied} content={retryTooltip}>
        <Button
          variant="secondary"
          onClick={isDisabled ? undefined : () => retryDialog.open(undefined)}
          isAriaDisabled={isDisabled}
        >
          Retry run
        </Button>
      </DisabledWithTooltip>
      <RetryExecutionDialog
        isOpen={retryDialog.isOpen}
        onClose={retryDialog.close}
        onConfirm={retry.handleRetry}
        confirmLoading={retry.isPending || isVersionLoading}
        isCurrentVersion={isCurrentVersion}
        isVersionLoading={isVersionLoading}
        versionLabel={versionLabel}
      />
    </>
  )
}
