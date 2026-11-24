import { Switch, Tooltip } from '@patternfly/react-core'
import type { IntegrationsAPI } from '@syntara/contracts'

type IntegrationRead = IntegrationsAPI.components['schemas']['IntegrationRead']

type IntegrationEnabledSwitchProps = Readonly<{
  integration: IntegrationRead
  switchId: string
  canUpdate: boolean
  isPermissionsLoading: boolean
  updateDeniedTooltip: string
  onToggle: () => void
}>

/** Enable/disable switch for non–execution-plane integrations. */
export function IntegrationEnabledSwitch({
  integration,
  switchId,
  canUpdate,
  isPermissionsLoading,
  updateDeniedTooltip,
  onToggle,
}: IntegrationEnabledSwitchProps) {
  const isEnabled = integration.enabled ?? true
  const label = isEnabled ? 'Enabled' : 'Disabled'
  const ariaLabel = `Toggle ${integration.name}`

  if (isPermissionsLoading || !canUpdate) {
    return (
      <Tooltip content={updateDeniedTooltip}>
        <Switch id={switchId} label={label} isChecked={isEnabled} isDisabled aria-label={ariaLabel} />
      </Tooltip>
    )
  }

  return <Switch id={switchId} label={label} isChecked={isEnabled} onChange={onToggle} aria-label={ariaLabel} />
}
