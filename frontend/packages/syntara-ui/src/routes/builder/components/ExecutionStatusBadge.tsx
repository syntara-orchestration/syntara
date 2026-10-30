import { Icon, Spinner } from '@patternfly/react-core'
import {
  RhUiCheckCircleFillIcon,
  RhUiClockIcon,
  RhUiEllipsisHorizontalFillIcon,
  RhUiMinusCircleFillIcon,
  RhUiStopCircleFillIcon,
  RhUiErrorFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum } from '@syntara/contracts'

import type { ActivityStatus } from '../../../routes/workflows/execution/types'
import { activityStatusColors } from '../executionStatusConstants'

export const EXECUTION_BADGE_DATA_ATTR = 'data-execution-badge'
export const EXECUTION_BADGE_SELECTOR = `[${EXECUTION_BADGE_DATA_ATTR}]`

type ExecutionStatusBadgeProps = {
  status: ActivityStatus
  retryCount?: number
  nodeType?: string
  /** True when this step reused a previous run's output instead of executing. */
  replayed?: boolean
}

type VisualStatus = 'pending' | 'running' | 'waiting' | 'success' | 'error' | 'skipped' | 'cancelled'

const visualStatusConfig: Record<
  VisualStatus,
  {
    color: string
    node: React.ReactNode
    borderStyle?: React.CSSProperties['borderStyle']
  }
> = {
  pending: {
    color: activityStatusColors.pending,
    node: <RhUiEllipsisHorizontalFillIcon style={{ color: activityStatusColors.pending }} />,
  },
  running: {
    color: activityStatusColors.running,
    node: (
      <Spinner size="lg" style={{ '--pf-v6-c-spinner--Color': activityStatusColors.running } as React.CSSProperties} />
    ),
  },
  waiting: {
    color: activityStatusColors.waiting,
    node: <RhUiClockIcon style={{ color: activityStatusColors.waiting }} />,
  },
  success: {
    color: activityStatusColors.completed,
    node: <RhUiCheckCircleFillIcon style={{ color: activityStatusColors.completed }} />,
  },
  error: {
    color: activityStatusColors.failed,
    node: <RhUiErrorFillIcon style={{ color: activityStatusColors.failed }} />,
  },
  skipped: {
    color: activityStatusColors.skipped,
    node: <RhUiMinusCircleFillIcon style={{ color: activityStatusColors.skipped }} />,
    borderStyle: 'dashed',
  },
  cancelled: {
    color: activityStatusColors.cancelled,
    node: <RhUiStopCircleFillIcon style={{ color: activityStatusColors.cancelled }} />,
  },
}

function normalizeStatus(status: ActivityStatus, nodeType?: string): { visualStatus: VisualStatus; label: string } {
  switch (status) {
    case 'completed':
      return { visualStatus: 'success', label: 'Success' }
    case 'failed':
      return { visualStatus: 'error', label: 'Error' }
    case 'waiting':
      if (nodeType === ActivityTypeEnum.WAIT) {
        return { visualStatus: 'running', label: 'Running' }
      }
      return { visualStatus: 'waiting', label: 'Waiting for approval' }
    case 'retrying':
      return { visualStatus: 'running', label: 'Retrying' }
    case 'pending':
      return { visualStatus: 'pending', label: 'Pending' }
    case 'running':
      return { visualStatus: 'running', label: 'Running' }
    case 'skipped':
      return { visualStatus: 'skipped', label: 'Skipped' }
    case 'cancelled':
      return { visualStatus: 'cancelled', label: 'Cancelled' }
    default:
      return { visualStatus: 'pending', label: 'Pending' }
  }
}

/**
 * Visual indicator for activity execution status on workflow steps (canvas).
 * Renders as a circular badge positioned in the bottom-right corner of the step.
 *
 * A replayed step keeps its terminal status but gets a dashed ring and a
 * "reused" suffix, so a retried run does not read as though every step ran
 * again. The text carries the meaning rather than the ring alone.
 */
export function ExecutionStatusBadge({
  status,
  retryCount,
  nodeType,
  replayed = false,
}: Readonly<ExecutionStatusBadgeProps>) {
  const normalized = normalizeStatus(status, nodeType)
  const config = visualStatusConfig[normalized.visualStatus]

  const baseTitle = retryCount ? `${normalized.label} (${retryCount} retries)` : normalized.label
  const title = replayed ? `${baseTitle} — reused output from a previous run` : baseTitle
  const borderStyle = replayed ? 'dashed' : (config.borderStyle ?? 'solid')

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '-20px',
        right: '-20px',
        width: '48px',
        height: '48px',
        borderRadius: '50%',
        backgroundColor: 'var(--pf-t--global--background--color--primary--default)',
        borderColor: config.color,
        borderStyle,
        borderWidth: '2px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10,
      }}
      data-execution-badge=""
      data-replayed={replayed ? '' : undefined}
      title={title}
      role="img"
      aria-label={title}
    >
      {normalized.visualStatus === 'running' ? config.node : <Icon size="xl">{config.node}</Icon>}
    </div>
  )
}
