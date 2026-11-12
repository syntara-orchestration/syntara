import { RhUiCheckCircleIcon } from '@patternfly/react-icons'
import type { ExecutionPlaneAPI } from '@syntara/contracts'

import { IconLabel } from '../../components/IconLabel'
import type { KebabAction } from '../../components/SynKebabMenu'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

export function buildExecutionTargetTestConnectionAction(
  target: ExecutionTarget,
  onTestConnection: (target: ExecutionTarget) => void,
  options: { isDisabled?: boolean } = {}
): KebabAction {
  const isDisabled = Boolean(options.isDisabled)

  return {
    key: 'test-connection',
    title: <IconLabel icon={<RhUiCheckCircleIcon />}>Test connection</IconLabel>,
    isAriaDisabled: isDisabled,
    tooltipProps: isDisabled ? { content: 'Connection test in progress' } : undefined,
    onClick: isDisabled
      ? undefined
      : () => {
          onTestConnection(target)
        },
  }
}
