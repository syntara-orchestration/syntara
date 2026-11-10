/**
 * Distinguishing steps that reused a previous run's output against steps that
 * ran fresh in the current retry.
 *
 * The retry engine records a replayed completed step with the *source* run's
 * `started_at` / `completed_at`, so a completed step whose start precedes the
 * retry execution's own creation never ran in that execution — it reused the
 * source run's output. Unselected failures are also restored with the source
 * timestamps, but they have no successful output to reuse. The retry endpoint
 * also re-validates independently, so this is a display-only signal and never
 * gates behaviour.
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
 * Whether a step reused a previous run's successful output rather than running.
 *
 * Returns `false` whenever the answer is not provable — no baseline, no start
 * time (the step has not run yet), an unparseable timestamp, or a status other
 * than completed. Guessing here would mislabel a retained failure as reused
 * output, or a step that actually ran.
 */
export function isReplayedStep(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined,
  status: string | null | undefined
): boolean {
  if (status !== ACTIVITY_STATUS.COMPLETED) return false
  if (!replayBaselineAt || !startedAt) return false

  const started = Date.parse(startedAt)
  const baseline = Date.parse(replayBaselineAt)
  if (Number.isNaN(started) || Number.isNaN(baseline)) return false

  return started < baseline
}
