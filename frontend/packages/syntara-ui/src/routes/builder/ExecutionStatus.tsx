import {
  RhUiCheckCircleIcon,
  RhUiClockIcon,
  RhUiCloseCircleIcon,
  RhUiEllipsisHorizontalFillIcon,
  RhUiHourglassIcon,
  RhUiMinusCircleFillIcon,
  RhUiPauseCircleFillIcon,
  RhUiStopCircleFillIcon,
  RhUiSyncIcon,
  RhUiWarningFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum, type ExecutionsAPI } from '@syntara/contracts'
import type React from 'react'

import { SynLabel } from '../../components/labels/SynLabel'

import { activityStatusDisplayLabels, executionStatusDisplayLabels } from './executionStatusConstants'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']
type ActivityStatus = ExecutionsAPI.components['schemas']['ActivityStatus']

const statusMap: Record<ExecutionStatus, 'success' | 'danger' | 'warning' | 'info' | 'custom'> = {
  pending: 'custom',
  running: 'custom',
  paused: 'warning',
  completed: 'success',
  completed_with_errors: 'warning',
  failed: 'danger',
  cancelled: 'custom',
}

const statusIcons: Record<ExecutionStatus, React.ComponentType<{ className?: string }>> = {
  pending: RhUiHourglassIcon,
  running: RhUiSyncIcon,
  paused: RhUiPauseCircleFillIcon,
  completed: RhUiCheckCircleIcon,
  completed_with_errors: RhUiWarningFillIcon,
  failed: RhUiCloseCircleIcon,
  cancelled: RhUiStopCircleFillIcon,
}

export function StatusLabel({ status }: Readonly<{ status: ExecutionStatus }>) {
  const IconComponent = statusIcons[status]

  return (
    <SynLabel variant="outline" status={statusMap[status]} icon={<IconComponent />}>
      {executionStatusDisplayLabels[status]}
    </SynLabel>
  )
}

const activityStatusVariant: Record<ActivityStatus, 'success' | 'danger' | 'warning' | 'info' | 'custom'> = {
  pending: 'custom',
  running: 'custom',
  waiting: 'warning',
  completed: 'success',
  failed: 'danger',
  retrying: 'warning',
  skipped: 'custom',
  cancelled: 'custom',
}

const activityStatusIcons: Record<ActivityStatus, React.ComponentType<{ className?: string }>> = {
  pending: RhUiEllipsisHorizontalFillIcon,
  running: RhUiSyncIcon,
  waiting: RhUiClockIcon,
  completed: RhUiCheckCircleIcon,
  failed: RhUiCloseCircleIcon,
  retrying: RhUiSyncIcon,
  skipped: RhUiMinusCircleFillIcon,
  cancelled: RhUiStopCircleFillIcon,
}

export function ActivityStatusLabel({ status, nodeType }: Readonly<{ status: ActivityStatus; nodeType?: string }>) {
  if (nodeType === ActivityTypeEnum.WAIT && status === 'waiting') {
    return (
      <SynLabel variant="outline" status="custom" icon={<RhUiSyncIcon />}>
        Running
      </SynLabel>
    )
  }

  const IconComponent = activityStatusIcons[status] ?? RhUiEllipsisHorizontalFillIcon
  const variant = activityStatusVariant[status] ?? 'custom'
  const displayLabel = activityStatusDisplayLabels[status] ?? status.charAt(0).toUpperCase() + status.slice(1)

  return (
    <SynLabel variant="outline" status={variant} icon={<IconComponent />}>
      {displayLabel}
    </SynLabel>
  )
}
