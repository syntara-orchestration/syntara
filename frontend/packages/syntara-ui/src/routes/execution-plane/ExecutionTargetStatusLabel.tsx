import { Tooltip } from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiMinusCircleIcon, RhUiSyncIcon } from '@patternfly/react-icons'

import { SynLabel } from '../../components/labels/SynLabel'
import { capitalize } from '../../utils/capitalize'

type StatusVisual = {
  status: 'success' | 'danger' | 'warning' | 'info' | 'custom'
  Icon: React.ComponentType<{ className?: string }>
}

/** Visuals keyed by EP `TargetStatus` values. Unknown statuses use DEFAULT_VISUAL. */
const STATUS_VISUAL: Record<string, StatusVisual> = {
  registering: { status: 'info', Icon: RhUiSyncIcon },
  validating: { status: 'info', Icon: RhUiSyncIcon },
  bootstrapping: { status: 'info', Icon: RhUiSyncIcon },
  active: { status: 'success', Icon: RhUiCheckCircleIcon },
  degraded: { status: 'warning', Icon: RhUiSyncIcon },
  draining: { status: 'custom', Icon: RhUiMinusCircleIcon },
  failed: { status: 'danger', Icon: RhUiCloseCircleIcon },
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
