import { Tooltip } from '@patternfly/react-core'

import { SynLabel } from '../../../components/labels/SynLabel'

/**
 * MVP: only one Execution plane infrastructure (OpenShift) integration is supported,
 * and its state cannot be toggled in the UI. Shown in place of the enable/disable switch
 * on the list, and as the State field on the detail page.
 */
export const EXECUTION_PLANE_ENABLED_TOOLTIP =
  'Execution plane infrastructure must stay enabled so execution targets can use the cluster. Its state cannot be toggled. Connection health appears in Status.'

type ExecutionPlaneEnabledStateProps = Readonly<{
  enabled?: boolean | null
}>

export function ExecutionPlaneEnabledState({ enabled = true }: ExecutionPlaneEnabledStateProps) {
  const label = enabled ? 'Enabled' : 'Disabled'

  return (
    <Tooltip content={EXECUTION_PLANE_ENABLED_TOOLTIP}>
      <SynLabel color="grey" tabIndex={0}>
        {label}
      </SynLabel>
    </Tooltip>
  )
}
