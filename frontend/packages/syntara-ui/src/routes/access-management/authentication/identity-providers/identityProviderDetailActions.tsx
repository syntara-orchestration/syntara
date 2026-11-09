import { RhUiBanIcon, RhUiEditIcon, RhUiTrashIcon } from '@patternfly/react-icons'

import { IconLabel } from '../../../../components/IconLabel'
import type { KebabAction } from '../../../../components/SynKebabMenu'
import { useIdentityProviderPermissions } from '../useIdentityProviderPermissions'

export function buildIdentityProviderKebabActions(
  idpPermissions: ReturnType<typeof useIdentityProviderPermissions>,
  onEditMapping: () => void,
  onRevoke: () => void,
  onDelete: () => void
): KebabAction[] {
  return [
    {
      key: 'edit-mapping',
      title: <IconLabel icon={<RhUiEditIcon />}>Edit group mapping</IconLabel>,
      isAriaDisabled: !idpPermissions.canUpdate,
      tooltipProps: idpPermissions.canUpdate ? undefined : { content: idpPermissions.tooltips.update },
      onClick: idpPermissions.canUpdate ? onEditMapping : undefined,
    },
    {
      key: 'revoke',
      title: <IconLabel icon={<RhUiBanIcon />}>Revoke tokens</IconLabel>,
      isAriaDisabled: !idpPermissions.canRevoke,
      tooltipProps: idpPermissions.canRevoke ? undefined : { content: idpPermissions.tooltips.revoke },
      onClick: idpPermissions.canRevoke ? onRevoke : undefined,
    },
    { key: 'separator', isSeparator: true },
    {
      key: 'delete',
      title: <IconLabel icon={<RhUiTrashIcon />}>Delete provider</IconLabel>,
      isDanger: true,
      isAriaDisabled: !idpPermissions.canDelete,
      tooltipProps: idpPermissions.canDelete ? undefined : { content: idpPermissions.tooltips.delete },
      onClick: idpPermissions.canDelete ? onDelete : undefined,
    },
  ]
}
