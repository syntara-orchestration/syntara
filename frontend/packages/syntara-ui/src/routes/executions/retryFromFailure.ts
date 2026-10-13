import { ExecutionStatusEnum } from '@syntara/contracts'
import type { ExecutionsAPI } from '@syntara/contracts'

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
export function isRetryFromFailureEligible(
  status: ExecutionStatus | null | undefined,
  mode?: string | null
): boolean {
  if (!status) return false
  if (mode === 'test') return false
  return RETRY_FROM_FAILURE_STATUSES.has(status)
}

/** Failure points the preview says will actually run, in backend-reported order. */
export function eligibleRetryPointIds(preview: RetryFromFailurePreview | undefined): string[] {
  return preview?.eligible_point_ids ?? []
}

/**
 * Copy for the confirmation body. The preview deliberately returns no
 * node-by-node breakdown, so this never claims more detail than the API gives.
 */
export function describeRetryScope(preview: RetryFromFailurePreview | undefined): string {
  const total = preview?.total_step_count ?? 0
  const points = eligibleRetryPointIds(preview).length

  if (points === 0) {
    return 'No failed steps were found to retry from.'
  }

  const stepNoun = total === 1 ? 'step' : 'steps'
  const pointNoun = points === 1 ? 'failure point' : 'failure points'

  if (total === 0) {
    return `Retrying will resume at ${points} ${pointNoun}. No additional steps need to re-run.`
  }

  return `Retrying will resume at ${points} ${pointNoun} and re-run ${total} ${stepNoun}. Steps that already completed keep their output.`
}

/** Whether the dialog's confirm button should be enabled. */
export function canConfirmRetryFromFailure(
  preview: RetryFromFailurePreview | undefined,
  isLoading: boolean,
  isError: boolean
): boolean {
  if (isLoading || isError) return false
  return preview?.eligible === true && eligibleRetryPointIds(preview).length > 0
}