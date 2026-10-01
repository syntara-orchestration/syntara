import { Content, ContentVariants, Icon, Spinner } from '@patternfly/react-core'
import {
  RhUiCheckCircleFillIcon,
  RhUiClockIcon,
  RhUiEllipsisHorizontalFillIcon,
  RhUiMinusCircleFillIcon,
  RhUiStopCircleFillIcon,
  RhUiErrorFillIcon,
} from '@patternfly/react-icons'
import { ActivityTypeEnum } from '@syntara/contracts'

import { useElapsedTime } from '../../../hooks/useElapsedTime'
import type { ActivityStatus } from '../../../routes/workflows/execution/types'
import { formatElapsedTime } from '../../../utils/dateUtils'
import { activityStatusColors, getActivityStatusDisplayLabel } from '../executionStatusConstants'

export const EXECUTION_BADGE_DATA_ATTR = 'data-execution-badge'
export const EXECUTION_BADGE_SELECTOR = `[${EXECUTION_BADGE_DATA_ATTR}]`

type ExecutionStatusBadgeProps = {
  status: ActivityStatus
  retryCount?: number
  nodeType?: string
  /** When a form prompt is waiting, elapsed time is shown under the badge icon. */
  startedAt?: string
}

const BADGE_ANCHOR_STYLE: React.CSSProperties = {
  position: 'absolute',
  bottom: '-20px',
  right: '-20px',
  width: '48px',
  height: '48px',
  zIndex: 10,
  overflow: 'visible',
}

const BADGE_CIRCLE_STYLE: React.CSSProperties = {
  width: '100%',
  height: '100%',
  borderRadius: '50%',
  backgroundColor: 'var(--pf-t--global--background--color--primary--default)',
  borderWidth: '2px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  boxSizing: 'border-box',
}

const WAITING_ELAPSED_LABEL_STYLE: React.CSSProperties = {
  position: 'absolute',
  top: '100%',
  left: '50%',
  transform: 'translateX(-50%)',
  marginTop: 'var(--pf-t--global--spacer--xs)',
  fontSize: 'var(--pf-t--global--font--size--body--sm)',
  color: 'var(--pf-t--global--text--color--regular)',
  lineHeight: 1.2,
  whiteSpace: 'nowrap',
}

function shouldShowFormPromptWaitingElapsed(status: ActivityStatus, nodeType?: string, startedAt?: string): boolean {
  return status === 'waiting' && nodeType === ActivityTypeEnum.FORM_PROMPT && !!startedAt
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
      return {
        visualStatus: 'waiting',
        label: getActivityStatusDisplayLabel('waiting', nodeType),
      }
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
 */
export function ExecutionStatusBadge({ status, retryCount, nodeType, startedAt }: Readonly<ExecutionStatusBadgeProps>) {
  const normalized = normalizeStatus(status, nodeType)
  const config = visualStatusConfig[normalized.visualStatus]
  const showWaitingElapsed = shouldShowFormPromptWaitingElapsed(status, nodeType, startedAt)
  const { elapsedMs } = useElapsedTime(startedAt, undefined, showWaitingElapsed)
  const elapsedLabel = elapsedMs !== undefined ? formatElapsedTime(elapsedMs) : undefined

  const title = retryCount ? `${normalized.label} (${retryCount} retries)` : normalized.label
  const accessibleLabel = showWaitingElapsed && elapsedLabel ? `${title}, elapsed ${elapsedLabel}` : title

  return (
    // eslint-disable-next-line syntara/prefer-pf-text-components -- fixed-size anchor for canvas status badge placement
    <div style={BADGE_ANCHOR_STYLE}>
      {/* eslint-disable-next-line syntara/prefer-pf-text-components -- circular canvas status icon container, not text */}
      <div
        style={{
          ...BADGE_CIRCLE_STYLE,
          borderColor: config.color,
          borderStyle: config.borderStyle ?? 'solid',
        }}
        data-execution-badge=""
        title={accessibleLabel}
        role="img"
        aria-label={accessibleLabel}
      >
        {normalized.visualStatus === 'running' ? config.node : <Icon size="xl">{config.node}</Icon>}
      </div>
      {showWaitingElapsed && elapsedLabel ? (
        <Content component={ContentVariants.small} style={WAITING_ELAPSED_LABEL_STYLE} aria-hidden="true">
          {elapsedLabel}
        </Content>
      ) : null}
    </div>
  )
}
