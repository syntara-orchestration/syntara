/**
 * Distinguish steps that reused a previous run's output from steps that ran
 * fresh in the current retry.
 *
 * The retry engine records a replayed completed step with the *source* run's
 * `started_at` / `completed_at`, so a completed step whose start precedes the
 * retry execution's own creation never ran in that execution — it reused the
 * source run's output. A retained failure can also have reusable partial
 * output; only mark it when that output is present. The retry endpoint also
 * re-validates independently, so this is a display-only signal and never gates
 * behaviour.
 */

import { ACTIVITY_STATUS } from './executionState/executionHelpers'

/**
 * The timestamp replayed steps predate, or `null` when this execution is not a
 * retry and therefore has no replayed steps to show.
 */
export function resolveRetryReplayBaseline(
  executionCreatedAt: string | null | undefined,
  retriedFromExecutionId: string | null | undefined
): string | null {
  if (!retriedFromExecutionId) return null
  return executionCreatedAt ?? null
}

/**
 * Whether a step reused output from a previous run rather than running.
 *
 * Returns `false` whenever the answer is not provable — no baseline, no start
 * time (the step has not run yet), an unparseable timestamp, or a status that
 * cannot have restored output. A failed step needs nonempty output data because
 * it can be retained with partial output.
 */
export function isReplayedStep(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined,
  status: string | null | undefined,
  outputData?: Record<string, unknown> | null
): boolean {
  const hasReusableStatus =
    status === ACTIVITY_STATUS.COMPLETED ||
    (status === ACTIVITY_STATUS.FAILED && outputData != null && Object.keys(outputData).length > 0)
  if (!hasReusableStatus) return false
  if (!replayBaselineAt || !startedAt) return false

  const started = Date.parse(startedAt)
  const baseline = Date.parse(replayBaselineAt)
  if (Number.isNaN(started) || Number.isNaN(baseline)) return false

  return started < baseline
}
