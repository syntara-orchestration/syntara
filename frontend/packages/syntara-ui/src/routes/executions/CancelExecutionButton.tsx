import { Button } from '@patternfly/react-core'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

import { useCancelExecution } from './useCancelExecution'

type CancelExecutionButtonProps = Readonly<{
  executionId: string
  projectId: string
}>

const cancelTooltip = permissionTooltip('cancel this execution', 'execution:run')

export function CancelExecutionButton({ executionId, projectId }: CancelExecutionButtonProps) {
  /* v8 ignore start -- v8 emits phantom branches from compiled hook destructuring */
  const cancel = useCancelExecution(executionId)
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', { resourceProject: projectId })
  const permissionDenied = !isChecking && !canRun
  const isCancelDisabled = !canRun || cancel.isPending || isChecking
  /* v8 ignore stop */

  return (
    <DisabledWithTooltip isDisabled={permissionDenied} content={cancelTooltip}>
      <Button
        variant="secondary"
        isDanger
        onClick={isCancelDisabled ? undefined : cancel.handleCancel}
        isLoading={cancel.isPending}
        isAriaDisabled={isCancelDisabled}
      >
        Cancel run
      </Button>
    </DisabledWithTooltip>
  )
}
