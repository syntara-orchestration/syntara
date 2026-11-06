import { RhUiEditIcon } from '@patternfly/react-icons'
import type { ExecutionPlaneAPI } from '@syntara/contracts'

import { IconLabel } from '../../components/IconLabel'
import type { KebabAction } from '../../components/SynKebabMenu'

import type { ExecutionTargetPermissions } from './useExecutionTargetPermissions'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetRead']

export function buildExecutionTargetEditAction(
  target: ExecutionTarget,
  permissions: ExecutionTargetPermissions,
  onEdit: (target: ExecutionTarget) => void
): KebabAction {
  return {
    key: 'edit',
    title: <IconLabel icon={<RhUiEditIcon />}>Edit execution target</IconLabel>,
    isAriaDisabled: !permissions.canUpdate,
    tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.update },
    onClick: permissions.canUpdate
      ? () => {
          onEdit(target)
        }
      : undefined,
  }
}
