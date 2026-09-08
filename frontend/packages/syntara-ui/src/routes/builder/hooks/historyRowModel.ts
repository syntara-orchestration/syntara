import type { ExecutionsAPI } from '@syntara/contracts'

import { formatDateTime, formatElapsedTime } from '../../../utils/dateUtils'
import { isExecutionRetryable } from '../../executions/executionRetryable'
import type { ExecutionMetadata } from '../../workflows/stores/useExecutionStore'
import { formatHistoryDateTime } from '../historyDateUtils'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']
type BadgeVersionStatus = 'published' | 'previously_published'

const TRUNCATED_ID_LENGTH = 8

type ExecutionLike = {
  id?: string | null
  created_at?: string | null
  completed_at?: string | null
  status?: string | null
  mode?: string | null
  workflow_id?: string | null
  workflow_version?: number | null
  workflow_version_name?: string | null
  workflow_version_created_at?: string | null
  retried_from_execution_id?: string | null
  approval_pending?: boolean | null
  execution_metadata?: ExecutionMetadata | null
}

export type ExecutionHistoryRowModel = {
  datetimeLabel: string | null
  showRetryKebab: boolean
  elapsedLabel: string
  runIdLabel: string | null
  versionHref: string | null
  versionLabel: string | null
  retriedFromLabel: string | null
  status: string | null | undefined
  showTestRun: boolean
  approvalPending: boolean | undefined
}

export function buildExecutionHistoryRowModel(
  execution: ExecutionLike,
  elapsedMs: number | undefined
): ExecutionHistoryRowModel {
  const truncatedId = execution.id ? execution.id.slice(0, TRUNCATED_ID_LENGTH) : null
  const hasVersion = execution.workflow_version != null && Boolean(execution.workflow_id)
  const versionLabel = hasVersion
    ? (execution.workflow_version_name ?? formatDateTime(execution.workflow_version_created_at))
    : null

  return {
    datetimeLabel: execution.created_at ? formatHistoryDateTime(execution.created_at) : null,
    showRetryKebab: isExecutionRetryable(execution.status as ExecutionStatus | null | undefined, execution.mode),
    elapsedLabel: elapsedMs !== undefined ? `Elapsed time: ${formatElapsedTime(elapsedMs)}` : 'Elapsed time: -',
    runIdLabel: truncatedId ? `Run ID: ${truncatedId}` : null,
    versionHref: hasVersion
      ? `/workflow-builder/${execution.workflow_id}?version=${String(execution.workflow_version)}`
      : null,
    versionLabel,
    retriedFromLabel: execution.retried_from_execution_id
      ? `Retried from: ${execution.retried_from_execution_id.slice(0, TRUNCATED_ID_LENGTH)}`
      : null,
    status: execution.status,
    showTestRun: execution.execution_metadata?.mode === 'test',
    approvalPending: execution.approval_pending ?? undefined,
  }
}

export function shouldShowSecondaryVersionDatetime(
  name: string | null | undefined,
  createdAt: string | null | undefined
): boolean {
  return Boolean(name && createdAt)
}

export function resolveVersionStatusForBadge(status: string | null | undefined): BadgeVersionStatus | null {
  if (status === 'published' || status === 'previously_published') {
    return status
  }
  return null
}

export function workflowVersionHref(workflowId: string, version: number): string {
  return `/workflow-builder/${workflowId}?version=${String(version)}`
}

export function executionDetailHref(executionId: string): string {
  return `/executions/${executionId}`
}

export function getClearFiltersHandler<T>(
  onFilterChange: ((filters: T[]) => void) | undefined
): (() => void) | undefined {
  if (!onFilterChange) {
    return undefined
  }
  return () => onFilterChange([])
}
