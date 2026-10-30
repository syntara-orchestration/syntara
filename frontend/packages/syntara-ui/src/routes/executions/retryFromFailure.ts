import { ExecutionStatusEnum } from '@syntara/contracts'
import type { ExecutionsAPI } from '@syntara/contracts'

import { getActivityTypeLabel } from '../builder/panels/utils/getUpstreamStepDisplayName'
import { parseCompositeKey } from '../workflows/execution/utils/activityState'

type ExecutionStatus = ExecutionsAPI.components['schemas']['ExecutionStatus']

export type RetryFromFailurePreview = ExecutionsAPI.components['schemas']['RetryFromFailureValidationResponse']

/**
 * Terminal states the backend will accept a retry-from-failure for. Kept
 * separate from `isExecutionRetryable`, which also allows `completed` and
 * `cancelled` for a full re-run — resuming past completed steps is only
 * meaningful when something actually failed.
 */
const RETRY_FROM_FAILURE_STATUSES: ReadonlySet<ExecutionStatus> = new Set([
  ExecutionStatusEnum.FAILED,
  ExecutionStatusEnum.COMPLETED_WITH_ERRORS,
])

/**
 * Whether the execution detail header should offer "Retry from failure".
 *
 * This is the optimistic gate only. The backend re-validates independently on
 * both the preview and the retry call, so a `true` here never promises the
 * retry will be accepted.
 */
export function isRetryFromFailureEligible(status: ExecutionStatus | null | undefined, mode?: string | null): boolean {
  if (!status) return false
  if (mode === 'test') return false
  return RETRY_FROM_FAILURE_STATUSES.has(status)
}

/** Failure points the preview says will actually run, in backend-reported order. */
export function eligibleRetryPointIds(preview: RetryFromFailurePreview | undefined): string[] {
  return preview?.eligible_point_ids ?? []
}

/** Use a selected failed node as the retry point; iteration rows map to their base node ID. */
export function selectedRetryPointId(
  selectedNodeId: string | null | undefined,
  preview: RetryFromFailurePreview | undefined
): string | undefined {
  if (!selectedNodeId) return undefined
  const baseId = parseCompositeKey(selectedNodeId).baseId
  const autoIncluded = preview?.auto_included_node_ids ?? []
  return eligibleRetryPointIds(preview).includes(baseId) && !autoIncluded.includes(baseId) ? baseId : undefined
}

export type RetryPlanPoint = Readonly<{
  id: string
  name: string
  typeLabel: string
  stepCount: number | undefined
}>

/** Resolve the preview's retry points to UI names without inferring downstream nodes. */
export function getRetryPlanPoints(
  preview: RetryFromFailurePreview | undefined,
  activityNameMap: ReadonlyMap<string, string>,
  activityTypeMap: ReadonlyMap<string, string> = new Map()
): RetryPlanPoint[] {
  return eligibleRetryPointIds(preview).map((id) => {
    const { baseId, iteration } = parseCompositeKey(id)
    const baseName = activityNameMap.get(baseId) ?? activityNameMap.get(id) ?? baseId
    const name = iteration === undefined ? baseName : `${baseName} (Iteration ${iteration + 1})`
    const type = activityTypeMap.get(baseId) ?? activityTypeMap.get(id)

    return {
      id,
      name,
      typeLabel: type ? (getActivityTypeLabel(type) ?? type) : 'Step',
      stepCount: preview?.step_count_by_eligible_point?.[id],
    }
  })
}

/** Whether the retry action should be enabled. */
export function canConfirmRetryFromFailure(
  preview: RetryFromFailurePreview | undefined,
  isLoading: boolean,
  isError: boolean
): boolean {
  if (isLoading || isError) return false
  return preview?.eligible === true && eligibleRetryPointIds(preview).length > 0
}
