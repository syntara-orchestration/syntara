import { Button, Switch, Tooltip } from '@patternfly/react-core'
import { RhUiEditIcon } from '@patternfly/react-icons'
import type { IntegrationsAPI } from '@syntara/contracts'

import { DisabledWithTooltip } from '../../../../components/DisabledWithTooltip'
import type { KebabAction } from '../../../../components/SynKebabMenu'
import { SynKebabMenu } from '../../../../components/SynKebabMenu'
import type { IntegrationPermissions } from '../useIntegrationPermissions'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

export function IntegrationToolbar({
  integration,
  kebabActions,
  onToggleEnabled,
  onEdit,
  editLabel,
  permissions,
}: Readonly<{
  integration: IntegrationRead
  kebabActions: KebabAction[]
  onToggleEnabled: () => void
  onEdit: () => void
  editLabel: string
  permissions: IntegrationPermissions
}>) {
  return (
    <>
      {permissions.isLoading || !permissions.canUpdate ? (
        <Tooltip content={permissions.tooltips.enable}>
          <Switch
            id="integration-enabled-toggle"
            label={integration.enabled ? 'Enabled' : 'Disabled'}
            isChecked={integration.enabled ?? true}
            isDisabled
            aria-label={`Toggle ${integration.name}`}
          />
        </Tooltip>
      ) : (
        <Switch
          id="integration-enabled-toggle"
          label={integration.enabled ? 'Enabled' : 'Disabled'}
          isChecked={integration.enabled ?? true}
          onChange={onToggleEnabled}
          aria-label={`Toggle ${integration.name}`}
        />
      )}
      <DisabledWithTooltip isDisabled={!permissions.canUpdate} content={permissions.tooltips.update}>
        <Button
          variant="primary"
          icon={<RhUiEditIcon />}
          isAriaDisabled={!permissions.canUpdate}
          onClick={permissions.canUpdate ? onEdit : undefined}
        >
          {editLabel}
        </Button>
      </DisabledWithTooltip>
      <SynKebabMenu actions={kebabActions} aria-label="Integration actions" />
    </>
  )
}
