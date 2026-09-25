import { ActivityTypeEnum, type ExecutionsAPI } from '@syntara/contracts'

import type { ActivityStatus } from '../workflows/execution/types'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

export const executionStatusDisplayLabels: Record<ExecutionStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  paused: 'Paused',
  completed: 'Completed',
  completed_with_errors: 'Completed with errors',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

const statusColors: Record<ExecutionStatus, string> = {
  pending: 'var(--pf-t--global--color--nonstatus--gray--300)',
  running: 'var(--pf-t--global--color--brand--default)',
  paused: 'var(--pf-t--global--color--status--warning--default)',
  completed: 'var(--pf-t--global--color--status--success--default)',
  completed_with_errors: 'var(--pf-t--global--color--status--warning--default)',
  failed: 'var(--pf-t--global--color--status--danger--default)',
  cancelled: 'var(--pf-t--global--color--nonstatus--gray--300)',
}

export const activityStatusDisplayLabels: Record<ActivityStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  waiting: 'Waiting for approval',
  completed: 'Successful',
  failed: 'Failed',
  retrying: 'Retrying',
  skipped: 'Skipped',
  cancelled: 'Cancelled',
}

/** Human-facing activity status label; ``waiting`` depends on step type (approval vs form prompt). */
export function getActivityStatusDisplayLabel(status: ActivityStatus, nodeType?: string): string {
  if (status === 'waiting') {
    if (nodeType === ActivityTypeEnum.FORM_PROMPT) {
      return 'Waiting for input'
    }
    if (nodeType === ActivityTypeEnum.WAIT) {
      return 'Running'
    }
    return activityStatusDisplayLabels.waiting
  }
  const label = activityStatusDisplayLabels[status as ActivityStatus]
  if (label) {
    return label
  }
  return status.charAt(0).toUpperCase() + status.slice(1)
}

export const activityStatusColors: Record<ActivityStatus, string> = {
  pending: statusColors.pending,
  running: statusColors.running,
  waiting: statusColors.paused,
  completed: statusColors.completed,
  failed: statusColors.failed,
  retrying: statusColors.running,
  skipped: 'var(--pf-t--global--color--nonstatus--gray--default)',
  cancelled: statusColors.cancelled,
}
