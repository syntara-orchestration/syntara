/**
 * Distinguishing steps that were replayed from a previous run against steps
 * that ran fresh in the current retry.
 *
 * The retry engine records a replayed step with the *source* run's
 * `started_at` / `completed_at`, so a step whose start precedes the retry
 * execution's own creation never ran in that execution — it reused the source
 * run's output. The retry endpoint also re-validates independently, so this is
 * a display-only signal and never gates behaviour.
 */

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
 * Whether a step's recorded start time proves it was replayed rather than run.
 *
 * Returns `false` whenever the answer is not provable — no baseline, no start
 * time (the step has not run yet), or an unparseable timestamp. Guessing here
 * would mislabel a step that actually ran.
 */
export function isReplayedStep(
  startedAt: string | null | undefined,
  replayBaselineAt: string | null | undefined
): boolean {
  if (!replayBaselineAt || !startedAt) return false

  const started = Date.parse(startedAt)
  const baseline = Date.parse(replayBaselineAt)
  if (Number.isNaN(started) || Number.isNaN(baseline)) return false

  return started < baseline
}