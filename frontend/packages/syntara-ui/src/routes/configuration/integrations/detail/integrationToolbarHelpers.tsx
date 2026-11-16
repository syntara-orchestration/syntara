import { RhUiCheckCircleIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'
import type { useNavigate } from '@tanstack/react-router'

import { IconLabel } from '../../../../components/IconLabel'
import type { KebabAction } from '../../../../components/SynKebabMenu'
import { detachPromise } from '../../../../utils/detachPromise'
import { canEditIntegrationFully } from '../integrationUtils'
import type { useIntegrationActions } from '../useIntegrationActions'
import type { IntegrationPermissions } from '../useIntegrationPermissions'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export function getEditToolbarProps(
  integration: IntegrationRead,
  editPath: string,
  navigate: ReturnType<typeof useNavigate>,
  renameDialog: ReturnType<typeof useIntegrationActions>['renameDialog']
) {
  if (!canEditIntegrationFully(integration)) {
    return {
      editLabel: 'Edit name',
      onEdit: () => renameDialog.open(integration),
    }
  }
  return {
    editLabel: 'Edit integration',
    onEdit: () => detachPromise(navigate({ to: editPath })),
  }
}

export function buildKebabActions(
  integration: IntegrationRead,
  validateDialog: { open: (item: IntegrationRead) => void },
  deleteDialog: { open: (item: IntegrationRead) => void },
  permissions: IntegrationPermissions
): KebabAction[] {
  return [
    {
      key: 'validate',
      title: <IconLabel icon={<RhUiCheckCircleIcon />}>Validate integration</IconLabel>,
      isAriaDisabled: !permissions.canUpdate,
      tooltipProps: permissions.canUpdate ? undefined : { content: permissions.tooltips.validate },
      onClick: permissions.canUpdate ? () => validateDialog.open(integration) : undefined,
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete integration</IconLabel>,
      isDanger: true,
      isAriaDisabled: !permissions.canDelete,
      tooltipProps: permissions.canDelete ? undefined : { content: permissions.tooltips.delete },
      onClick: permissions.canDelete ? () => deleteDialog.open(integration) : undefined,
    },
  ]
}
