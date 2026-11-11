import { RhUiWarningFillIcon } from '@patternfly/react-icons'
import { use } from 'react'

import { SynLabel } from '../../../components/labels/SynLabel'
import { useElapsedTime } from '../../../hooks/useElapsedTime'
import type { ActivityState, ActivityStatus } from '../../workflows/execution/types'

import { ExpectedDurationContext } from './expectedDurationContext'

export function ActivityRunningLongWarning({
  state,
  nodeType,
  expectedDuration,
}: Readonly<{
  state?: ActivityState
  nodeType?: string
  expectedDuration?: number
}>) {
  return (
    <RunningLongWarning
      status={state?.status ?? 'pending'}
      nodeType={nodeType}
      startedAt={state?.startedAt}
      completedAt={state?.completedAt}
      expectedDuration={expectedDuration}
    />
  )
}

export function RunningLongWarning({
  status,
  nodeType,
  startedAt,
  completedAt,
  expectedDuration,
}: Readonly<{
  status: ActivityStatus
  nodeType?: string
  startedAt?: string | null
  completedAt?: string | null
  expectedDuration?: number | null
}>) {
  const systemDefault = use(ExpectedDurationContext)
  const threshold = expectedDuration ?? systemDefault
  const active = status === 'running' || status === 'retrying' || (status === 'waiting' && nodeType === 'wait')
  const { elapsedMs } = useElapsedTime(startedAt, completedAt, active)
  if (
    !active ||
    completedAt ||
    threshold == null ||
    !Number.isFinite(threshold) ||
    threshold <= 0 ||
    elapsedMs === undefined ||
    elapsedMs < threshold * 1000
  )
    return null
  return (
    <span role="status" title="Expected duration exceeded. This warning does not stop the run.">
      <SynLabel status="warning" variant="outline" icon={<RhUiWarningFillIcon />}>
        Running long
      </SynLabel>
    </span>
  )
}
