import { Tooltip } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiMinusCircleIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLabel } from '../../components/labels/SynLabel'
import { capitalize } from '../../utils/capitalize'

type StatusVisual = {
  status: 'success' | 'danger' | 'warning' | 'custom'
  Icon: React.ComponentType<{ className?: string }>
}

const STATUS_VISUAL: Record<string, StatusVisual> = {
  ready: { status: 'success', Icon: RhUiCheckCircleIcon },
  available: { status: 'success', Icon: RhUiCheckCircleIcon },
  active: { status: 'success', Icon: RhUiCheckCircleIcon },
  healthy: { status: 'success', Icon: RhUiCheckCircleIcon },
  error: { status: 'danger', Icon: RhUiCloseCircleIcon },
  failed: { status: 'danger', Icon: RhUiCloseCircleIcon },
  unavailable: { status: 'danger', Icon: RhUiCloseCircleIcon },
  pending: { status: 'warning', Icon: RhUiSyncIcon },
  provisioning: { status: 'warning', Icon: RhUiSyncIcon },
  syncing: { status: 'warning', Icon: RhUiSyncIcon },
  deleting: { status: 'custom', Icon: RhUiMinusCircleIcon },
  disabled: { status: 'custom', Icon: RhUiMinusCircleIcon },
}

const DEFAULT_VISUAL: StatusVisual = { status: 'custom', Icon: RhUiMinusCircleIcon }

type ExecutionTargetStatusLabelProps = Readonly<{
  status: string
  message?: string | null
}>

/** Status label for an execution target row from the Execution Plane facade. */
export function ExecutionTargetStatusLabel({ status, message }: ExecutionTargetStatusLabelProps) {
  const visual = STATUS_VISUAL[status.toLowerCase()] ?? DEFAULT_VISUAL
  const { status: labelStatus, Icon } = visual
  const labelText = capitalize(status.replaceAll('_', ' '))

  const label = (
    <SynLabel variant="outline" status={labelStatus} icon={<Icon />} tabIndex={message ? 0 : undefined}>
      {labelText}
    </SynLabel>
  )

  if (message) {
    return <Tooltip content={message}>{label}</Tooltip>
  }

  return label
}
