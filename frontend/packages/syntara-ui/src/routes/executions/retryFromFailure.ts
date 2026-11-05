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

/** Use a selected eligible node as the retry point; iteration rows map to their base node ID. */
export function selectedRetryPointId(
  selectedNodeId: string | null | undefined,
  preview: RetryFromFailurePreview | undefined
): string | undefined {
  if (!selectedNodeId) return undefined
  const baseId = parseCompositeKey(selectedNodeId).baseId
  return eligibleRetryPointIds(preview).includes(baseId) ? baseId : undefined
}

/** Sanitized nodes that replace failed start points, independent of the current selection. */
export function sanitizedReplacementIds(preview: RetryFromFailurePreview | undefined): string[] {
  return [...new Set(Object.values(preview?.sanitized_replacements ?? {}).flat())]
}

/** Sanitized start points on the current retry path that cannot reuse stored output. */
export function unavailableOutputIds(preview: RetryFromFailurePreview | undefined): string[] {
  if (!preview?.eligible) return []
  const replacements = new Set(sanitizedReplacementIds(preview))
  const autoIncluded = preview.auto_included_node_ids ?? []
  const eligible = preview.eligible_point_ids ?? []
  return [...new Set([...autoIncluded, ...eligible.filter((id) => replacements.has(id))])]
}

/** Failed nodes replaced by the current unavailable sanitized outputs. */
export function replacedFailedNodeIds(
  preview: RetryFromFailurePreview | undefined,
  unavailableIds: readonly string[]
): string[] {
  const unavailable = new Set(unavailableIds)
  return Object.entries(preview?.sanitized_replacements ?? {})
    .filter(([, ids]) => ids.some((id) => unavailable.has(id)))
    .map(([failedId]) => failedId)
}

export function joinDisplayNames(names: readonly string[]): string {
  if (names.length <= 1) return names[0] ?? ''
  if (names.length === 2) return `${names[0]} and ${names[1]}`
  return `${names.slice(0, -1).join(', ')}, and ${names[names.length - 1]}`
}

/** Visible warning when the retry must regenerate sanitized output. */
export function getSanitizedOutputWarning(
  preview: RetryFromFailurePreview | undefined,
  activityNameMap: ReadonlyMap<string, string>
): string | undefined {
  const unavailableIds = unavailableOutputIds(preview)
  if (unavailableIds.length === 0) return undefined

  const sanitizedNames = unavailableIds.map((id) => activityNameMap.get(id) ?? id)
  const replacedNames = replacedFailedNodeIds(preview, unavailableIds).map((id) => activityNameMap.get(id) ?? id)
  const sanitizedList = joinDisplayNames(sanitizedNames)
  const verb = sanitizedNames.length === 1 ? 'was' : 'were'
  if (replacedNames.length === 0) {
    return `Output from ${sanitizedList} ${verb} sanitized and cannot be reused. The retry will begin at ${sanitizedList} to regenerate the missing input.`
  }
  return `Output from ${sanitizedList} ${verb} sanitized and cannot be reused. The retry will begin at ${sanitizedList} to regenerate the missing input for ${joinDisplayNames(replacedNames)}.`
}

export type RetryPlanPoint = Readonly<{
  id: string
  name: string
  typeLabel: string
  stepCount: number | undefined
  sanitizedFailedNodeNames: string[]
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
    const sanitizedFailedNodeNames = Object.entries(preview?.sanitized_replacements ?? {})
      .filter(([, replacementIds]) =>
        replacementIds.some((replacementId) => parseCompositeKey(replacementId).baseId === baseId)
      )
      .map(([failedId]) => {
        const failedBaseId = parseCompositeKey(failedId).baseId
        return activityNameMap.get(failedBaseId) ?? activityNameMap.get(failedId) ?? failedBaseId
      })

    return {
      id,
      name,
      typeLabel: type ? (getActivityTypeLabel(type) ?? type) : 'Step',
      stepCount: preview?.step_count_by_eligible_point?.[id],
      sanitizedFailedNodeNames: [...new Set(sanitizedFailedNodeNames)],
    }
  })
}

/** Retry plan rows for sanitized outputs on the current retry path. */
export function getUnavailableRetryPlanPoints(
  preview: RetryFromFailurePreview | undefined,
  activityNameMap: ReadonlyMap<string, string>,
  activityTypeMap: ReadonlyMap<string, string> = new Map()
): RetryPlanPoint[] {
  if (!preview) return []
  return getRetryPlanPoints(
    { ...preview, eligible_point_ids: unavailableOutputIds(preview) },
    activityNameMap,
    activityTypeMap
  )
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
