import { RhUiTrashIcon } from '@patternfly/react-icons'
import type { ExecutionPlaneAPI } from '@syntara/contracts'

import { IconLabel } from '../../components/IconLabel'
import type { KebabAction } from '../../components/SynKebabMenu'

import type { ExecutionTargetPermissions } from './useExecutionTargetPermissions'

type ExecutionTarget = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

export function buildExecutionTargetDeleteAction(
  target: ExecutionTarget | undefined,
  deleteDialog: { open: (item: ExecutionTarget) => void },
  permissions: ExecutionTargetPermissions
): KebabAction {
  return {
    key: 'delete',
    title: <IconLabel icon={<RhUiTrashIcon />}>Delete execution target</IconLabel>,
    isDanger: true,
    isAriaDisabled: !permissions.canDelete,
    tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
    onClick:
      permissions.canDelete && target
        ? () => {
            deleteDialog.open(target)
          }
        : undefined,
  }
}
