import { Button, DropdownItem } from '@patternfly/react-core'

import { DisabledWithTooltip } from '../../components/DisabledWithTooltip'
import { permissionTooltip } from '../../hooks/permissionUtils'
import { useCanI } from '../../hooks/useCanI'

type RetryFromFailureButtonProps = Readonly<{
  projectId: string
  onClick?: () => void
  asDropdownItem?: boolean
}>

const retryTooltip = permissionTooltip('retry this execution from failure', 'execution:run')

/**
 * "Retry from failure" action for a failed execution.
 *
 * Opens the in-context retry review panel. Rendered only for executions the
 * backend accepts a retry-from-failure for; see `isRetryFromFailureEligible`.
 */
export function RetryFromFailureButton({ projectId, onClick, asDropdownItem = false }: RetryFromFailureButtonProps) {
  /* v8 ignore start -- v8 emits phantom branches from the compiled hook destructuring */
  const { allowed: canRun, isChecking } = useCanI('run', 'execution', { resourceProject: projectId })
  const permissionDenied = !isChecking && !canRun
  const isDisabled = !canRun || isChecking
  /* v8 ignore stop */

  return (
    asDropdownItem ? (
      <DropdownItem
        value="retry-from-failure"
        onClick={isDisabled ? undefined : onClick}
        isAriaDisabled={isDisabled}
        tooltipProps={permissionDenied ? { content: retryTooltip } : undefined}
        data-testid="retry-from-failure-button"
      >
        Retry from failure
      </DropdownItem>
    ) : (
      <DisabledWithTooltip isDisabled={permissionDenied} content={retryTooltip}>
        <Button
          variant="secondary"
          onClick={isDisabled ? undefined : onClick}
          isAriaDisabled={isDisabled}
          data-testid="retry-from-failure-button"
        >
          Retry from failure
        </Button>
      </DisabledWithTooltip>
    )
  )
}
