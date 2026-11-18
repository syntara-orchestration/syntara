import { Stack, StackItem } from '@patternfly/react-core'
import {
  RhUiCheckCircleIcon,
  RhUiClockIcon,
  RhUiCloseCircleIcon,
  RhUiEllipsisHorizontalFillIcon,
  RhUiHourglassIcon,
  RhUiHistoryIcon,
  RhUiMinusCircleFillIcon,
  RhUiPauseCircleFillIcon,
  RhUiStopCircleFillIcon,
  RhUiSyncIcon,
  RhUiWarningFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum, type ExecutionsAPI } from '@syntara/contracts'
import type React from 'react'

import { ReplayedOutputBadge } from '../../components/labels/ReplayedOutputBadge'
import { SynLabel } from '../../components/labels/SynLabel'
import { capitalize } from '../../utils/capitalize'

import styles from './ExecutionStatus.module.css'
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

/**
 * @param replayed True when this activity reused a previous run's output
 * instead of executing in this retry. Appends `ReplayedOutputBadge` next to
 * the status label, matching the canvas treatment in `ExecutionStatusBadge`.
 */
export function ActivityStatusLabel({
  status,
  nodeType,
  replayed = false,
  retainedFailure = false,
  triggerInputReused = false,
}: Readonly<{
  status: ActivityStatus
  nodeType?: string
  replayed?: boolean
  retainedFailure?: boolean
  triggerInputReused?: boolean
}>) {
  const isRunningWait = nodeType === ActivityTypeEnum.WAIT && status === 'waiting'

  const IconComponent = activityStatusIcons[status] ?? RhUiEllipsisHorizontalFillIcon
  const variant = activityStatusVariant[status] ?? 'custom'
  const displayLabel = activityStatusDisplayLabels[status] ?? capitalize(status)
  const statusLabel = isRunningWait ? (
    <SynLabel variant="outline" status="custom" icon={<RhUiSyncIcon />}>
      Running
    </SynLabel>
  ) : (
    <SynLabel variant="outline" status={variant} icon={<IconComponent />}>
      {displayLabel}
    </SynLabel>
  )

  if (!retainedFailure && !replayed && !triggerInputReused) return statusLabel

  return (
    <Stack className={styles.activityStatusDetails} role="group" aria-label="Activity status and retry information">
      <StackItem>{statusLabel}</StackItem>
      <ActivityStatusRetryMarkers
        retainedFailure={retainedFailure}
        replayed={replayed}
        triggerInputReused={triggerInputReused}
      />
    </Stack>
  )
}

/** Renders retry markers as StackItems so callers can control their placement. */
function ActivityStatusRetryMarkers({
  replayed = false,
  retainedFailure = false,
  triggerInputReused = false,
}: Readonly<{
  replayed?: boolean
  retainedFailure?: boolean
  triggerInputReused?: boolean
}>) {
  return (
    <>
      {retainedFailure && (
        <StackItem>
          <SynLabel variant="outline" status="warning">
            Retained failure
          </SynLabel>
        </StackItem>
      )}
      {replayed && (
        <StackItem>
          <ReplayedOutputBadge />
        </StackItem>
      )}
      {triggerInputReused && (
        <StackItem>
          <SynLabel variant="outline" icon={<RhUiHistoryIcon />}>
            Reused trigger input
          </SynLabel>
        </StackItem>
      )}
    </>
  )
}
